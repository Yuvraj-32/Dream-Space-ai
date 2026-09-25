"""Doors and windows from CAD symbols, attached to (and bridging) walls. Metres, Y up.

Doors: a door block's (or a loose) ~90° swing arc gives the hinge (arc centre)
and width (radius); the arc end lying along the wall marks the closed door,
so the opening spans hinge -> that end. Loose arcs are only accepted when both
the hinge and that end sit on a wall line — that keeps round furniture out.

Windows: window blocks, or small groups of window-layer lines, lying on a wall.

Walls come out of walls.py split at every opening (the face lines stop at the
gap). Each opening re-joins the wall pieces on either side of its gap into one
wall, so the 3D view shows a wall with a door cut out (lintel above) instead
of a full-height hole.
"""
import math
import re

DOOR_HINTS = ("door", "puert", "porte")
DOOR_EXACT = ("dr", "drs")
WINDOW_HINTS = ("window", "ventan", "glaz", "fenet", "wind")
WINDOW_EXACT = ("win", "wdw")
ON_WALL_TOL = 0.20      # m beyond the wall's half thickness
SPAN_REACH = 1.50       # an opening may sit in a gap up to this far past a wall piece's end
BRIDGE_GAP = 0.30       # join wall pieces whose ends are this close to the opening


def _hint(name, prefixes, exact):
    return any(tok in exact or tok.startswith(prefixes) for tok in re.findall(r"[a-z0-9]+", (name or "").lower()))


def is_door_name(name):
    return _hint(name, DOOR_HINTS, DOOR_EXACT)


def is_window_name(name):
    return _hint(name, WINDOW_HINTS, WINDOW_EXACT)


def _frame(w):
    dx, dy = w[2] - w[0], w[3] - w[1]
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    return L, ux, uy, -uy, ux


def _locate(px, py, walls):
    """Nearest wall line carrying point P: (index, t along wall, perpendicular dist)."""
    best = None
    for i, w in enumerate(walls):
        L, ux, uy, nx, ny = _frame(w)
        t = (px - w[0]) * ux + (py - w[1]) * uy
        d = abs((px - w[0]) * nx + (py - w[1]) * ny)
        if d > w[4] / 2.0 + ON_WALL_TOL or t < -SPAN_REACH or t > L + SPAN_REACH:
            continue
        outside = max(0.0, -t, t - L)
        key = (outside > 0, d + outside)
        if best is None or key < best[0]:
            best = (key, i, t, d)
    return None if best is None else best[1:]


def _door_from_arc(arc, walls):
    """arc = (cx, cy, r, sweep, sx, sy, ex, ey) in metres -> opening or None."""
    cx, cy, r, sweep = arc[0], arc[1], arc[2], arc[3]
    if not (80.0 <= sweep <= 100.0 and 0.5 <= r <= 1.3):
        return None
    hinge = _locate(cx, cy, walls)
    if hinge is None:
        return None
    # Which arc end lies along the hinge's wall? That's the closed-door position.
    ends = [(arc[4], arc[5]), (arc[6], arc[7])]
    best = None
    for ex, ey in ends:
        loc = _locate(ex, ey, walls)
        if loc and loc[0] == hinge[0] and (best is None or loc[2] < best[1][2]):
            best = ((ex, ey), loc)
    if best is None:
        return None
    (ex, ey), _ = best
    return {"type": "door", "x": (cx + ex) / 2.0, "y": (cy + ey) / 2.0, "width": r}


def _extent_on_wall(points, wall):
    L, ux, uy, nx, ny = _frame(wall)
    ts = [(x - wall[0]) * ux + (y - wall[1]) * uy for x, y in points]
    return min(ts), max(ts)


def _group_segments(segs, link=0.05):
    """Connected groups of short segments (a window symbol is 2–4 parallel lines)."""
    parent = list(range(len(segs)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    boxes = [(min(s[0], s[2]) - link, min(s[1], s[3]) - link, max(s[0], s[2]) + link, max(s[1], s[3]) + link)
             for s in segs]
    order = sorted(range(len(segs)), key=lambda i: boxes[i][0])
    for n, i in enumerate(order):
        for j in order[n + 1:]:
            if boxes[j][0] > boxes[i][2]:
                break
            if boxes[j][1] <= boxes[i][3] and boxes[i][1] <= boxes[j][3]:
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(segs)):
        groups.setdefault(root(i), []).append(segs[i])
    return list(groups.values())


def _window_from_points(points, walls):
    cx = sum(p[0] for p in points) / len(points)
    cy = sum(p[1] for p in points) / len(points)
    loc = _locate(cx, cy, walls)
    if loc is None:
        return None
    lo, hi = _extent_on_wall(points, walls[loc[0]])
    width = hi - lo
    if not 0.3 <= width <= 4.0:
        return None
    L, ux, uy, _, _ = _frame(walls[loc[0]])
    w = walls[loc[0]]
    mid = (lo + hi) / 2.0
    return {"type": "window", "x": w[0] + ux * mid, "y": w[1] + uy * mid, "width": width}


def find_openings(walls, door_arcs, door_blocks, window_blocks, window_segs):
    """walls: [(x1,y1,x2,y2,t)] m. door_arcs: loose arc tuples. door_blocks /
    window_blocks: list of dicts {"arcs": [...], "points": [(x,y)...]} per block.
    window_segs: loose window-layer segments. Returns (walls, openings)."""
    found = []
    for blk in door_blocks:
        doors = [d for d in (_door_from_arc(a, walls) for a in blk["arcs"]) if d]
        if doors:
            found.extend(doors)
        elif blk["points"]:
            win = _window_from_points(blk["points"], walls)
            if win:
                win["type"] = "door"
                found.append(win)
    for a in door_arcs:
        d = _door_from_arc(a, walls)
        if d:
            found.append(d)
    for blk in window_blocks:
        if blk["points"]:
            win = _window_from_points(blk["points"], walls)
            if win:
                found.append(win)
    for g in _group_segments(window_segs):
        pts = [p for s in g for p in ((s[0], s[1]), (s[2], s[3]))]
        win = _window_from_points(pts, walls)
        if win:
            found.append(win)

    walls = [list(w) for w in walls]
    openings = []
    for op in sorted(found, key=lambda o: o["type"] != "door"):  # doors win overlaps
        walls, placed = _place(op, walls)
        if placed is None:
            continue
        if any(_overlap(o, placed) for o in openings):
            _merge_into(openings, placed)
            continue
        openings.append(placed)
    return [tuple(w) for w in walls], openings


def _place(op, walls):
    """Attach opening to a wall line, joining the wall pieces around its gap."""
    loc = _locate(op["x"], op["y"], walls)
    if loc is None:
        return walls, None
    i = loc[0]
    L, ux, uy, nx, ny = _frame(walls[i])
    base = walls[i]
    t_mid = loc[1]
    a, b = t_mid - op["width"] / 2.0, t_mid + op["width"] / 2.0
    lo, hi = min(0.0, a), max(L, b)
    thick = base[4]
    absorbed = {i}
    for j, v in enumerate(walls):
        if j == i:
            continue
        Lv, vx, vy, _, _ = _frame(v)
        if abs(ux * vy - uy * vx) > math.sin(math.radians(2.0)):
            continue
        off = ((v[0] + v[2]) / 2.0 - base[0]) * nx + ((v[1] + v[3]) / 2.0 - base[1]) * ny
        if abs(off) > (thick + v[4]) / 2.0 + 0.02:
            continue
        t1 = (v[0] - base[0]) * ux + (v[1] - base[1]) * uy
        t2 = (v[2] - base[0]) * ux + (v[3] - base[1]) * uy
        v_lo, v_hi = min(t1, t2), max(t1, t2)
        if v_lo <= b + BRIDGE_GAP and v_hi >= a - BRIDGE_GAP:
            lo, hi = min(lo, v_lo), max(hi, v_hi)
            thick = max(thick, v[4])
            absorbed.add(j)
    joined = [base[0] + ux * lo, base[1] + uy * lo, base[0] + ux * hi, base[1] + uy * hi, thick]
    walls = [w for j, w in enumerate(walls) if j not in absorbed] + [joined]
    t = t_mid - lo
    # Wall indices shift as pieces are joined, so openings keep coordinates only;
    # attach_indices() links them to their final wall.
    return walls, {"type": op["type"], "x": joined[0] + ux * t, "y": joined[1] + uy * t,
                   "width": op["width"]}


def _overlap(o, p):
    return math.hypot(o["x"] - p["x"], o["y"] - p["y"]) < (o["width"] + p["width"]) / 2.0 + 0.05


def _merge_into(openings, p):
    for o in openings:
        if _overlap(o, p):
            if o["type"] == "door" and p["type"] == "door":  # double door: two leaves
                o["x"], o["y"] = (o["x"] + p["x"]) / 2.0, (o["y"] + p["y"]) / 2.0
                o["width"] = o["width"] + p["width"]
            return


def attach_indices(walls, openings):
    """Final pass: point each opening at the wall that now carries it."""
    out = []
    for o in openings:
        loc = _locate(o["x"], o["y"], [list(w) for w in walls])
        if loc is not None:
            out.append({**o, "wall_index": loc[0]})
    return out
