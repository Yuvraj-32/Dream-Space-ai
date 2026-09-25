"""Split a CAD sheet into separate drawings and rank how plan-like each one is.

Phase 0 showed most files are whole sheets (floor plan + elevations + roof +
sections, sometimes two floors side by side), often with a border frame and
stray objects far away that wreck the overall extents. So:

1. Rasterize every line-bearing record onto a sparse 1 m grid and take
   8-connected components: drawings more than ~1–2 m apart separate.
2. Drop closed rectangles that act as sheet frames (they would glue every
   drawing inside them into one blob).
3. Discard tiny components (stray points, symbols) — that's what fixes the
   outlier-extents problem.
4. Rank the rest by floor-plan evidence: parallel wall-line pairs, room-name
   labels, door-swing arcs, wall-layer share.
"""
import math

import numpy as np

from .layers import paired_fraction, _is_door_arc
from .vocab import room_type_for

CELL_M = 0.5  # drawings more than ~1 m apart separate (two copies of a plan ~1 m apart merged at 1.0)
MIN_CLUSTER_SIDE_M = 2.0
MIN_CLUSTER_SEGMENTS = 8  # segments, not entities: one closed polyline can be a whole house outline
MIN_FRAME_SIDE_M = 5.0
MAX_CLUSTERS = 12
_KIND_ORDER = {"floor_plan": 0, "plan_without_walls": 1, "possible_plan": 2, "other_drawing": 3}
_MAX_SAMPLES = 6_000_000
_NON_GEOMETRY = {"TEXT", "MTEXT", "DIMENSION", "HATCH"}


def _components(records, idxs, cell):
    """Connected components (lists of record indices) of the given records."""
    seg_rows, owners, point_rows = [], [], []
    for i in idxs:
        r = records[i]
        if r.segs:
            seg_rows.extend(r.segs)
            owners.extend([i] * len(r.segs))
        elif r.bbox:
            cx, cy = r.center
            point_rows.append((cx, cy, i))
    if not seg_rows and not point_rows:
        return []

    xs_list, ys_list, own_list = [], [], []
    if seg_rows:
        s = np.asarray(seg_rows, dtype=np.float64)
        own = np.asarray(owners, dtype=np.int64)
        dx, dy = s[:, 2] - s[:, 0], s[:, 3] - s[:, 1]
        step = cell * 0.5
        n = np.maximum(1, np.ceil(np.hypot(dx, dy) / step)).astype(np.int64)
        while (n + 1).sum() > _MAX_SAMPLES:
            step *= 2
            n = np.maximum(1, np.ceil(np.hypot(dx, dy) / step)).astype(np.int64)
        reps = n + 1
        seg_idx = np.repeat(np.arange(len(s)), reps)
        starts = np.repeat(np.cumsum(reps) - reps, reps)
        t = (np.arange(reps.sum()) - starts) / n[seg_idx]
        xs_list.append(s[seg_idx, 0] + t * dx[seg_idx])
        ys_list.append(s[seg_idx, 1] + t * dy[seg_idx])
        own_list.append(own[seg_idx])
    if point_rows:
        p = np.asarray(point_rows, dtype=np.float64)
        xs_list.append(p[:, 0])
        ys_list.append(p[:, 1])
        own_list.append(p[:, 2].astype(np.int64))

    cx = np.floor(np.concatenate(xs_list) / cell).astype(np.int64)
    cy = np.floor(np.concatenate(ys_list) / cell).astype(np.int64)
    owner = np.concatenate(own_list)
    cx -= cx.min() - 1
    cy -= cy.min() - 1
    width = int(cy.max()) + 3
    keys = cx * width + cy
    uniq, inverse = np.unique(keys, return_inverse=True)

    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    rows, cols = [], []
    for off in (width, 1, width + 1, width - 1):
        pos = np.searchsorted(uniq, uniq + off)
        pos_clipped = np.minimum(pos, len(uniq) - 1)
        hit = uniq[pos_clipped] == uniq + off
        rows.append(np.nonzero(hit)[0])
        cols.append(pos_clipped[hit])
    # Samples of the same record must share a component even if (rarely) not adjacent.
    order = np.argsort(owner, kind="stable")
    same = owner[order][1:] == owner[order][:-1]
    rows.append(inverse[order][1:][same])
    cols.append(inverse[order][:-1][same])
    r = np.concatenate(rows)
    c = np.concatenate(cols)
    graph = coo_matrix((np.ones(len(r), dtype=np.int8), (r, c)), shape=(len(uniq), len(uniq)))
    _, cell_label = connected_components(graph, directed=False)

    rec_label = {}
    for o, lab in zip(owner.tolist(), cell_label[inverse].tolist()):
        rec_label.setdefault(o, lab)
    groups = {}
    for rec_i, lab in rec_label.items():
        groups.setdefault(lab, []).append(rec_i)
    return list(groups.values())


def _rect_bbox(rec):
    """bbox if the record is a closed, axis-aligned 4-sided polyline, else None."""
    if rec.kind not in ("LWPOLYLINE", "POLYLINE") or not rec.segs or len(rec.segs) not in (4, 5):
        return None
    x0, y0, x1, y1 = rec.bbox
    w, h = x1 - x0, y1 - y0
    if w <= 0 or h <= 0:
        return None
    eps = 1e-3 * max(w, h)
    for sx, sy, ex, ey in rec.segs:
        if abs(sx - ex) > eps and abs(sy - ey) > eps:
            return None
        for px, py in ((sx, sy), (ex, ey)):
            if not ((abs(px - x0) < eps or abs(px - x1) < eps) and (abs(py - y0) < eps or abs(py - y1) < eps)):
                return None
    first, last = rec.segs[0], rec.segs[-1]
    if math.hypot(first[0] - last[2], first[1] - last[3]) > eps:
        return None
    return rec.bbox


def _is_significant(records, group, total, metres_per_unit):
    if len(group) < max(10, 0.02 * total):
        return False
    return _bbox_of(records, group, metres_per_unit)[1] >= 3.0


def _bbox_of(records, group, metres_per_unit):
    b = [records[i].bbox for i in group]
    x0 = min(v[0] for v in b); y0 = min(v[1] for v in b)
    x1 = max(v[2] for v in b); y1 = max(v[3] for v in b)
    return (x0, y0, x1, y1), max(x1 - x0, y1 - y0) * metres_per_unit


def find_frames(records, geo_idxs, metres_per_unit, cell):
    """Indices of closed rectangles that frame several separate drawings."""
    min_side = MIN_FRAME_SIDE_M / metres_per_unit
    candidates = []
    for i in geo_idxs:
        rb = _rect_bbox(records[i])
        if rb and (rb[2] - rb[0]) >= min_side and (rb[3] - rb[1]) >= min_side:
            candidates.append((i, rb))
    candidates.sort(key=lambda c: (c[1][2] - c[1][0]) * (c[1][3] - c[1][1]), reverse=True)

    frames = set()
    for i, (x0, y0, x1, y1) in candidates[:20]:
        inside = [j for j in geo_idxs
                  if j != i and j not in frames
                  and x0 < records[j].center[0] < x1 and y0 < records[j].center[1] < y1]
        if len(inside) < 20:
            continue
        (cx0, cy0, cx1, cy1), _ = _bbox_of(records, inside, metres_per_unit)
        content_area = max(1e-9, (cx1 - cx0) * (cy1 - cy0))
        if (x1 - x0) * (y1 - y0) >= 1.5 * content_area:
            frames.add(i)
            continue
        comps = _components(records, inside, cell)
        if sum(1 for g in comps if _is_significant(records, g, len(inside), metres_per_unit)) >= 2:
            frames.add(i)
    return frames


def find_clusters(records, metres_per_unit, layer_roles):
    """Return (clusters, stats). Each cluster dict has a private "_records" list
    of record indices (stripped before sending to the client)."""
    cell = CELL_M / metres_per_unit
    geo_idxs = [i for i, r in enumerate(records) if r.bbox and r.kind not in _NON_GEOMETRY]
    frames = find_frames(records, geo_idxs, metres_per_unit, cell)
    geo_idxs = [i for i in geo_idxs if i not in frames]

    groups = _merge_nested(records, _components(records, geo_idxs, cell), metres_per_unit)
    kept, dropped_small = [], 0
    for g in groups:
        bbox, long_m = _bbox_of(records, g, metres_per_unit)
        n_segs = sum(len(records[i].segs) for i in g if records[i].segs)
        if long_m < MIN_CLUSTER_SIDE_M or n_segs < MIN_CLUSTER_SEGMENTS:
            dropped_small += 1
            continue
        kept.append({"_records": g, "bbox": bbox})

    _attach_annotations(records, kept, metres_per_unit)
    taken = {i for c in kept for i in c["_records"]}
    wallless = _label_only_clusters(records, taken, metres_per_unit)
    for c in kept + wallless:
        _score(records, c, metres_per_unit, layer_roles)
    for c in wallless:
        c["walls_missing"] = True
        c["kind_guess"] = "plan_without_walls"
    kept += wallless

    kept.sort(key=lambda c: (-_KIND_ORDER[c["kind_guess"]], c["score"]), reverse=True)
    kept = kept[:MAX_CLUSTERS]
    # Only auto-pick a confident floor plan; otherwise the user chooses (and the
    # UI shows why) rather than being handed an elevation or schedule table.
    best = next((c for c in kept if c["kind_guess"] == "floor_plan"), None)
    for n, c in enumerate(kept):
        c["id"] = f"c{n}"
        c["suggested"] = c is best
    return kept, {"frames_removed": len(frames), "tiny_groups_dropped": dropped_small,
                  "groups_found": len(groups)}


def _merge_nested(records, groups, metres_per_unit):
    """Fold every group lying entirely inside a bigger group's bbox into it.
    At a 0.5 m grid, furniture in mid-room or windows inside an elevation's
    facade are >1 m from the outline and come out as separate groups."""
    info = []
    for g in groups:
        bbox, long_m = _bbox_of(records, g, metres_per_unit)
        info.append([g, bbox, long_m, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1])])
    containers = sorted((row for row in info if row[2] >= MIN_CLUSTER_SIDE_M), key=lambda row: row[3])
    merged = []
    for row in sorted(info, key=lambda row: row[3]):
        g, (x0, y0, x1, y1), _, area = row
        host = next((c for c in containers
                     if c is not row and c[3] > area
                     and c[1][0] <= x0 and c[1][1] <= y0 and c[1][2] >= x1 and c[1][3] >= y1), None)
        if host is None:
            merged.append(row)
        else:
            host[0].extend(g)
    return [row[0] for row in merged]


def _attach_annotations(records, clusters, metres_per_unit):
    """Texts/dimensions/hatches aren't used for connectivity; hand each to the
    smallest cluster whose (slightly padded) bbox contains it."""
    pad = 0.5 / metres_per_unit
    boxes = [(c, (c["bbox"][0] - pad, c["bbox"][1] - pad, c["bbox"][2] + pad, c["bbox"][3] + pad))
             for c in clusters]
    boxes.sort(key=lambda cb: (cb[1][2] - cb[1][0]) * (cb[1][3] - cb[1][1]))
    for i, r in enumerate(records):
        if r.kind not in _NON_GEOMETRY or not r.bbox:
            continue
        x, y = r.center
        for c, (x0, y0, x1, y1) in boxes:
            if x0 <= x <= x1 and y0 <= y <= y1:
                c["_records"].append(i)
                break


def _label_only_clusters(records, taken, metres_per_unit, link_m=6.0, min_labels=3):
    """Room names with no wall geometry around them — Phase 1 found a plan whose
    walls LibreDWG dropped while keeping its labels and dimensions. Surface it
    (flagged) instead of silently hiding the user's floor plan."""
    labels = [i for i, r in enumerate(records)
              if i not in taken and r.text and room_type_for(r.text)]
    if len(labels) < min_labels:
        return []
    link = link_m / metres_per_unit
    parent = {i: i for i in labels}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for a_n, a in enumerate(labels):
        ax, ay = records[a].center
        for b in labels[a_n + 1:]:
            bx, by = records[b].center
            if abs(ax - bx) <= link and abs(ay - by) <= link:
                parent[root(a)] = root(b)
    groups = {}
    for i in labels:
        groups.setdefault(root(i), []).append(i)

    pad = 2.0 / metres_per_unit
    out = []
    for g in groups.values():
        if len(g) < min_labels:
            continue
        (x0, y0, x1, y1), _ = _bbox_of(records, g, metres_per_unit)
        box = (x0 - pad, y0 - pad, x1 + pad, y1 + pad)
        members = [i for i, r in enumerate(records)
                   if i not in taken and r.bbox
                   and box[0] <= r.center[0] <= box[2] and box[1] <= r.center[1] <= box[3]]
        (bx0, by0, bx1, by1), _ = _bbox_of(records, members, metres_per_unit)
        out.append({"_records": members, "bbox": (bx0, by0, bx1, by1)})
    return out


def _score(records, c, metres_per_unit, layer_roles):
    recs = [records[i] for i in c["_records"]]
    useful = [s for r in recs if r.segs and layer_roles.get(r.layer) != "ignore" for s in r.segs]
    if not useful:
        useful = [s for r in recs if r.segs for s in r.segs]
    total, axis_len, paired_len = paired_fraction(useful, metres_per_unit)
    pair_frac = paired_len / axis_len if axis_len else 0.0
    all_len = sum(math.hypot(s[2] - s[0], s[3] - s[1]) for r in recs if r.segs for s in r.segs)
    wall_len = sum(math.hypot(s[2] - s[0], s[3] - s[1])
                   for r in recs if r.segs and layer_roles.get(r.layer) == "wall" for s in r.segs)
    rooms = [r.text for r in recs if r.text and room_type_for(r.text)]
    door_arcs = sum(1 for r in recs if r.arc and _is_door_arc(r.arc, metres_per_unit))
    wall_share = wall_len / all_len if all_len else 0.0
    diag_frac = _long_diagonal_fraction(recs, metres_per_unit)

    score = (0.35 * min(1.0, pair_frac / 0.4)
             + 0.30 * min(1.0, len(rooms) / 3.0)
             + 0.20 * min(1.0, door_arcs / 2.0)
             + 0.15 * min(1.0, wall_share * 2.0)
             # Elevations/roof plans: sloped roof edges are long diagonal lines,
             # which floor plans almost never have. Also stops arched windows in
             # elevations (which look like door swings) outranking the real plan.
             - 0.5 * min(1.0, diag_frac / 0.3))
    long_m = max(c["bbox"][2] - c["bbox"][0], c["bbox"][3] - c["bbox"][1]) * metres_per_unit
    if long_m < 5.0:
        score *= long_m / 5.0  # schedules/tables/details: grid lines mimic wall pairs
    score = max(0.0, score)
    x0, y0, x1, y1 = c["bbox"]
    c.update({
        "size_m": [round((x1 - x0) * metres_per_unit, 1), round((y1 - y0) * metres_per_unit, 1)],
        "records": len(recs),
        "pair_frac": round(pair_frac, 2),
        "wall_share": round(wall_share, 2),
        "door_arcs": door_arcs,
        "diag_frac": round(diag_frac, 2),
        "room_labels": list(dict.fromkeys(rooms))[:8],
        "score": round(score, 2),
        # Parallel lines alone also fit site plans and structural grids; a
        # confident "floor_plan" needs room names or door swings too.
        "kind_guess": ("floor_plan" if score >= 0.45 and (rooms or door_arcs)
                       else "possible_plan" if score >= 0.25 else "other_drawing"),
        "walls_missing": False,
    })


def _long_diagonal_fraction(recs, metres_per_unit, min_len_m=1.0, tol_deg=5.0):
    """Share of long-line length (>= 1 m) that is neither horizontal nor vertical."""
    min_len = min_len_m / metres_per_unit
    tol = math.tan(math.radians(tol_deg))
    total = diag = 0.0
    for r in recs:
        if not r.segs:
            continue
        for s in r.segs:
            dx, dy = abs(s[2] - s[0]), abs(s[3] - s[1])
            length = math.hypot(dx, dy)
            if length < min_len:
                continue
            total += length
            if dy > dx * tol and dx > dy * tol:
                diag += length
    return diag / total if total else 0.0
