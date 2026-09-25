"""Wall centerlines (+ real thickness) from CAD wall-layer geometry, in metres.

Architectural CAD draws a wall as its two faces: parallel lines one wall
thickness apart. So walls are recovered by pairing parallel face lines, not
by image processing:

1. Pair each face line with its NEAREST parallel partner 6–65 cm away
   (nearest-partner avoids pairing a face with a plaster/cladding line
   further out as a second, phantom wall).
2. Merge collinear/overlapping pieces and bridge gaps <= 40 cm — the gap a
   partition leaves in the main wall's inner face at a T-junction.
   Door openings (>= ~60 cm) are left as gaps; openings.py re-bridges them.
3. Drawings that use single lines for walls (little pairing) fall back to
   using each line as a wall with a default thickness.
4. Curved walls: concentric ARC pairs -> short straight pieces along the arc.
5. Extend wall ends to meet the centerline of the wall they run into
   (L-corners, T-junctions): pairing stops each centerline at the inner face.

All coordinates here are metres, Y up. Output walls are dicts:
{"x1","y1","x2","y2","thickness"}.
"""
import math

MIN_T, MAX_T = 0.06, 0.65          # wall thickness range (m)
ANGLE_TOL_DEG = 2.0
MIN_OVERLAP = 0.10                 # m of shared length to count as a wall piece
MIN_SEG = 0.05                     # ignore tiny segments
GAP_BRIDGE = 0.40                  # merge collinear pieces across gaps up to this
SINGLE_LINE_T = 0.15               # thickness used for single-line walls
SINGLE_LINE_MIN_LEN = 0.30
EXTEND_MAX = 0.75                  # max end extension when closing junctions
ARC_STEP_DEG = 15.0


class _Line:
    __slots__ = ("x1", "y1", "x2", "y2", "L", "ux", "uy", "nx", "ny", "theta")

    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2
        dx, dy = x2 - x1, y2 - y1
        self.L = math.hypot(dx, dy)
        self.ux, self.uy = dx / self.L, dy / self.L
        self.nx, self.ny = -self.uy, self.ux
        self.theta = math.degrees(math.atan2(dy, dx)) % 180.0


def _angle_diff(a, b):
    d = abs(a - b) % 180.0
    return min(d, 180.0 - d)


def _subtract(interval, covered):
    """interval minus union(covered) -> list of pieces."""
    pieces = [interval]
    for c0, c1 in covered:
        nxt = []
        for a, b in pieces:
            if c1 <= a or c0 >= b:
                nxt.append((a, b))
                continue
            if c0 > a:
                nxt.append((a, c0))
            if c1 < b:
                nxt.append((c1, b))
        pieces = nxt
    return pieces


def pair_faces(segs):
    """Nearest-partner pairing of parallel face lines -> (pieces, paired_len, total_len).
    A piece is (x1, y1, x2, y2, thickness) in metres."""
    lines = [_Line(*s) for s in segs if math.hypot(s[2] - s[0], s[3] - s[1]) >= MIN_SEG]
    total = sum(l.L for l in lines)
    buckets = {}
    for idx, l in enumerate(lines):
        buckets.setdefault(int(round(l.theta)) % 180, []).append(idx)

    sin_tol = math.sin(math.radians(ANGLE_TOL_DEG))
    pieces, paired_len = [], 0.0
    all_cand = []
    for i, a in enumerate(lines):
        b0 = int(round(a.theta))
        cand = []
        for db in range(-2, 3):
            for j in buckets.get((b0 + db) % 180, ()):
                if j == i:
                    continue
                b = lines[j]
                if abs(a.ux * b.uy - a.uy * b.ux) > sin_tol:
                    continue
                # b in a's frame: offset along a's normal, interval along a's direction
                off1 = (b.x1 - a.x1) * a.nx + (b.y1 - a.y1) * a.ny
                off2 = (b.x2 - a.x1) * a.nx + (b.y2 - a.y1) * a.ny
                off = (off1 + off2) / 2.0
                # Either side: a wall drawn as a closed outline has its two faces
                # running in opposite directions, so "left of a" isn't reliable.
                if not (MIN_T <= abs(off) <= MAX_T):
                    continue
                t1 = (b.x1 - a.x1) * a.ux + (b.y1 - a.y1) * a.uy
                t2 = (b.x2 - a.x1) * a.ux + (b.y2 - a.y1) * a.uy
                lo, hi = max(0.0, min(t1, t2)), min(a.L, max(t1, t2))
                if hi - lo >= MIN_OVERLAP:
                    cand.append((off, lo, hi, j))
        all_cand.append(cand)

    modes = _thickness_modes(all_cand)
    usable = [[c for c in cands if _near_mode(abs(c[0]), modes)] for cands in all_cand]
    for i, a in enumerate(lines):
        cand = sorted(usable[i], key=lambda c: abs(c[0]))
        covered = []
        for off, lo, hi, j in cand:
            for p0, p1 in _subtract((lo, hi), covered):
                if p1 - p0 < MIN_OVERLAP or _partner_prefers_other(a, p0, p1, abs(off), i, lines[j], usable[j]):
                    continue
                cx, cy = a.x1 + a.nx * off / 2.0, a.y1 + a.ny * off / 2.0
                pieces.append((cx + a.ux * p0, cy + a.uy * p0, cx + a.ux * p1, cy + a.uy * p1, abs(off)))
                paired_len += p1 - p0
            covered.append((lo, hi))
    return pieces, paired_len, total, modes


def _partner_prefers_other(a, p0, p1, dist, i, b, b_cands):
    """Mutual-nearest check: pairing a->b over a's [p0, p1] is rejected if, over
    that same stretch, b has a closer partner than a. Stops an extra line
    (plaster, cladding, a parallel wall) outside a real wall pairing with the
    wall's nearer face as a phantom second wall."""
    q = [((a.x1 + a.ux * t) - b.x1) * b.ux + ((a.y1 + a.uy * t) - b.y1) * b.uy for t in (p0, p1)]
    lo, hi = min(q), max(q)
    for off, c_lo, c_hi, k in b_cands:
        if k != i and abs(off) < dist - 0.01 and min(hi, c_hi) - max(lo, c_lo) >= 0.5 * (p1 - p0):
            return True
    return False


def _thickness_modes(all_cand, bin_m=0.01, window=2, min_share=0.08, min_len_m=2.0):
    """Wall thicknesses this drawing actually uses (e.g. [0.15] or [0.115, 0.23]).
    Real wall pairs pile up at one or two spacings; accidental pairs (a face
    with the neighbouring wall, door leaves, closets) are scattered, so only
    well-supported histogram peaks are kept."""
    hist = {}
    for cand in all_cand:
        for off, lo, hi, _ in cand:
            k = int(round(abs(off) / bin_m))
            hist[k] = hist.get(k, 0.0) + (hi - lo)
    if not hist:
        return []
    total = sum(hist.values())
    smooth = {k: sum(hist.get(k + d, 0.0) for d in range(-window, window + 1)) for k in hist}
    modes = []
    for k, w in sorted(smooth.items(), key=lambda kv: -kv[1]):
        if w < max(min_share * total, min_len_m):
            break
        if all(abs(k - m) > 2 * window for m in modes):
            modes.append(k)
    return [m * bin_m for m in sorted(modes)]


def _near_mode(t, modes, tol=0.025):
    return any(abs(t - m) <= tol for m in modes)


def merge_collinear(walls):
    """Merge wall pieces whose bands overlap and whose spans touch (gap <= GAP_BRIDGE).
    walls: list of (x1, y1, x2, y2, t). Returns the same shape."""
    items = [list(w) for w in walls if math.hypot(w[2] - w[0], w[3] - w[1]) > 1e-6]
    changed = True
    while changed:
        changed = False
        items.sort(key=lambda w: -math.hypot(w[2] - w[0], w[3] - w[1]))
        out = []
        while items:
            a = items.pop(0)
            la = _Line(*a[:4])
            rest = []
            for b in items:
                lb = _Line(*b[:4])
                if _angle_diff(la.theta, lb.theta) > ANGLE_TOL_DEG:
                    rest.append(b)
                    continue
                off = ((b[0] + b[2]) / 2 - a[0]) * la.nx + ((b[1] + b[3]) / 2 - a[1]) * la.ny
                # Same wall only if the centerlines (nearly) coincide. Merging any
                # two overlapping bands let a wall swallow a cupboard/stair line
                # running beside it and grow into a 0.5 m+ bar.
                if abs(off) > 0.35 * min(a[4], b[4]) + 0.02:
                    rest.append(b)
                    continue
                t1 = (b[0] - a[0]) * la.ux + (b[1] - a[1]) * la.uy
                t2 = (b[2] - a[0]) * la.ux + (b[3] - a[1]) * la.uy
                lo, hi = min(t1, t2), max(t1, t2)
                if lo > la.L + GAP_BRIDGE or hi < -GAP_BRIDGE:
                    rest.append(b)
                    continue
                # Union the spans; keep the longer piece's line and the larger thickness.
                s0, s1 = min(0.0, lo), max(la.L, hi)
                a = [a[0] + la.ux * s0, a[1] + la.uy * s0, a[0] + la.ux * s1, a[1] + la.uy * s1, max(a[4], b[4])]
                la = _Line(*a[:4])
                changed = True
            items = rest
            out.append(a)
        items = out
    return [tuple(w) for w in items]


def arc_walls(arcs):
    """Concentric ARC pairs (curved walls) -> straight pieces along the mid radius.
    arcs: list of (cx, cy, r, sweep_deg, sx, sy, ex, ey) in metres."""
    out, used = [], set()
    for i, a in enumerate(arcs):
        if i in used:
            continue
        best = None
        for j, b in enumerate(arcs):
            if j == i or j in used:
                continue
            if math.hypot(a[0] - b[0], a[1] - b[1]) > 0.05:
                continue
            dr = abs(a[2] - b[2])
            if MIN_T <= dr <= MAX_T and (best is None or dr < best[1]):
                best = (j, dr)
        if best is None:
            continue
        j, dr = best
        used.update((i, j))
        outer = a if a[2] > arcs[j][2] else arcs[j]
        r = (a[2] + arcs[j][2]) / 2.0
        cx, cy = outer[0], outer[1]
        a0 = math.atan2(outer[5] - cy, outer[4] - cx)
        a1 = math.atan2(outer[7] - cy, outer[6] - cx)
        sweep = math.radians(outer[3])
        # Arcs run anticlockwise in their own frame; a mirrored block makes them
        # run clockwise in world space. Pick whichever direction reaches the end point.
        ccw = (a1 - a0) % (2 * math.pi)
        sign = 1.0 if abs(ccw - sweep) <= abs((2 * math.pi - ccw) - sweep) else -1.0
        n = max(1, int(math.ceil(outer[3] / ARC_STEP_DEG)))
        pts = [(cx + r * math.cos(a0 + sign * sweep * k / n), cy + r * math.sin(a0 + sign * sweep * k / n))
               for k in range(n + 1)]
        for p, q in zip(pts, pts[1:]):
            out.append((p[0], p[1], q[0], q[1], dr))
    return out, used


def extend_to_junctions(walls):
    """Move each free wall end onto the centerline of the wall it runs into."""
    walls = [list(w) for w in walls]
    for i, w in enumerate(walls):
        lw = _Line(*w[:4])
        for end in (0, 1):
            px, py = (w[0], w[1]) if end == 0 else (w[2], w[3])
            dx, dy = (-lw.ux, -lw.uy) if end == 0 else (lw.ux, lw.uy)
            best = None
            for j, v in enumerate(walls):
                if j == i:
                    continue
                lv = _Line(*v[:4])
                if _angle_diff(lw.theta, lv.theta) < 20.0:
                    continue
                denom = dx * lv.uy - dy * lv.ux
                if abs(denom) < 1e-9:
                    continue
                # Solve p + s*d = v0 + u*uv
                s = ((v[0] - px) * lv.uy - (v[1] - py) * lv.ux) / denom
                u = ((v[0] - px) * dy - (v[1] - py) * dx) / denom
                reach = min(EXTEND_MAX, v[4] / 2.0 + w[4] / 2.0 + 0.10)
                margin = v[4] / 2.0 + 0.10
                if -1e-6 <= s <= reach and -margin <= u <= lv.L + margin:
                    if best is None or s < best[0]:
                        best = (s, px + dx * s, py + dy * s)
            if best is not None and best[0] > 1e-6:
                if end == 0:
                    w[0], w[1] = best[1], best[2]
                else:
                    w[2], w[3] = best[1], best[2]
                lw = _Line(*w[:4])
    return [tuple(w) for w in walls]


def _drop_stairs(walls, max_len=1.8, min_chain=3):
    """Stair treads are parallel lines ~25–30 cm apart — the same signature as a
    wall's two faces — so a flight pairs into a ladder of short "walls". Short
    parallel pieces stacked a tread apart are linked; any chain of >= 3 is a
    stair and is dropped whole (ends included)."""
    short = [i for i, w in enumerate(walls) if math.hypot(w[2] - w[0], w[3] - w[1]) <= max_len]
    lines = {i: _Line(*walls[i][:4]) for i in short}
    parent = {i: i for i in short}

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for n, i in enumerate(short):
        a, la = walls[i], lines[i]
        for j in short[n + 1:]:
            if _angle_diff(la.theta, lines[j].theta) > ANGLE_TOL_DEG:
                continue
            b = walls[j]
            off = abs(((b[0] + b[2]) / 2 - a[0]) * la.nx + ((b[1] + b[3]) / 2 - a[1]) * la.ny)
            # Up to two treads apart: equidistant treads pair unevenly, so every
            # other gap can be missing from the ladder.
            if not 0.15 <= off <= 0.65:
                continue
            t1 = (b[0] - a[0]) * la.ux + (b[1] - a[1]) * la.uy
            t2 = (b[2] - a[0]) * la.ux + (b[3] - a[1]) * la.uy
            if min(la.L, max(t1, t2)) - max(0.0, min(t1, t2)) >= 0.5 * min(la.L, lines[j].L):
                parent[root(i)] = root(j)
    size = {}
    for i in short:
        size[root(i)] = size.get(root(i), 0) + 1
    stairs = {i for i in short if size[root(i)] >= min_chain}
    return [w for i, w in enumerate(walls) if i not in stairs]


def build_walls(segs, arcs):
    """segs: straight wall-layer segments (m); arcs: wall-layer ARC tuples (m).
    Returns (walls, info)."""
    pieces, paired, total, modes = pair_faces(segs)
    coverage = (paired / total) if total else 0.0
    mode = "double_line"
    if coverage < 0.30:
        mode = "single_line"
        pieces = [(s[0], s[1], s[2], s[3], SINGLE_LINE_T) for s in segs
                  if math.hypot(s[2] - s[0], s[3] - s[1]) >= SINGLE_LINE_MIN_LEN]
    curved, _ = arc_walls(arcs)
    walls = _drop_stairs(merge_collinear(pieces)) + curved
    # Drop squat pieces (columns, door-frame nubs): a wall is longer than it is thick.
    walls = [w for w in walls if math.hypot(w[2] - w[0], w[3] - w[1]) >= max(0.15, 1.5 * w[4])]
    walls = extend_to_junctions(walls)
    walls = merge_collinear(walls)
    return walls, {"mode": mode, "pair_coverage": round(coverage, 2), "curved_pieces": len(curved),
                   "thickness_modes_m": [round(m, 3) for m in modes]}
