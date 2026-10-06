"""Door leaf lines are not wall faces. Metres, Y up.

AutoCAD draws a door as its swing arc plus the leaf: a thin slab (one or two
parallel lines) running from the hinge toward an arc end, about one door width
long. Doors are usually drawn OPEN, so the leaf stands in the room, not in the
wall line. Wall detection pairs parallel lines, so the two lines of an open
leaf became a fake 0.15 m wall piece, and the door was then placed on it
instead of in the real gap in the wall.

Any straight line lying along a door arc's hinge -> arc-end direction (within
0.08 m sideways), starting at the hinge and running about one door width, is a
leaf; they are removed before walls are built. The wall opening is then a real
gap, and openings.py places the door in it.
"""
import math

START_SLACK = 0.15        # m: a leaf starts within this of the hinge (slab thickness)
LEN_MIN, LEN_MAX = 0.7, 1.3   # leaf length as a multiple of the arc radius
SIDE_TOL = 0.08           # m: how far off the hinge->end ray a leaf line may lie


def _is_leaf(s, hinge, end, r):
    dx, dy = end[0] - hinge[0], end[1] - hinge[1]
    n = math.hypot(dx, dy)
    if n < 1e-9:
        return False
    ux, uy = dx / n, dy / n
    ts, os_ = [], []
    for px, py in ((s[0], s[1]), (s[2], s[3])):
        rx, ry = px - hinge[0], py - hinge[1]
        ts.append(rx * ux + ry * uy)
        os_.append(rx * -uy + ry * ux)
    if max(abs(o) for o in os_) > SIDE_TOL:
        return False
    lo, hi = min(ts), max(ts)
    return -START_SLACK <= lo <= START_SLACK and LEN_MIN * r <= hi <= LEN_MAX * r


SLAB_MAX = 0.06           # m: a leaf slab's two lines are at most this far apart (a wall's are >= 0.075)
EXACT_TOL = 0.12          # a single leaf line may differ from the radius by this fraction


def _has_slab_partner(s, segs):
    """Another line parallel to `s`, 5-60 mm away, overlapping most of its length."""
    dx, dy = s[2] - s[0], s[3] - s[1]
    L = math.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    for o in segs:
        if o is s:
            continue
        ol = math.hypot(o[2] - o[0], o[3] - o[1])
        if ol < 0.5 * L or abs(ux * (o[3] - o[1]) - uy * (o[2] - o[0])) > 0.05 * ol:
            continue
        off = abs(((o[0] + o[2]) / 2 - s[0]) * -uy + ((o[1] + o[3]) / 2 - s[1]) * ux)
        if not 0.005 <= off <= SLAB_MAX:
            continue
        t1 = (o[0] - s[0]) * ux + (o[1] - s[1]) * uy
        t2 = (o[2] - s[0]) * ux + (o[3] - s[1]) * uy
        if min(L, max(t1, t2)) - max(0.0, min(t1, t2)) >= 0.6 * L:
            return True
    return False


def _is_exact_leaf(s, hinge, ends, r):
    """One line from the hinge to an arc end, one radius long."""
    L = math.hypot(s[2] - s[0], s[3] - s[1])
    if abs(L - r) > EXACT_TOL * r:
        return False
    for p, q in (((s[0], s[1]), (s[2], s[3])), ((s[2], s[3]), (s[0], s[1]))):
        if (math.hypot(p[0] - hinge[0], p[1] - hinge[1]) <= 0.06
                and any(math.hypot(q[0] - e[0], q[1] - e[1]) <= 0.06 for e in ends)):
            return True
    return False


def drop_door_leaves(segs, door_arcs):
    """segs: [(x1,y1,x2,y2)] m; door_arcs: arc tuples (cx,cy,r,sweep,sx,sy,ex,ey) m.
    Returns (kept_segs, number_dropped). A line is a leaf if it runs exactly hinge -> arc end,
    or lies along that direction as one line of a thin (<= 6 cm) double-line slab."""
    swings = [a for a in door_arcs if 80.0 <= a[3] <= 100.0 and 0.5 <= a[2] <= 1.3]
    if not swings:
        return segs, 0
    kept, dropped = [], 0
    for s in segs:
        leaf = False
        for a in swings:
            hinge, ends = (a[0], a[1]), ((a[4], a[5]), (a[6], a[7]))
            if _is_exact_leaf(s, hinge, ends, a[2]) or (
                    any(_is_leaf(s, hinge, e, a[2]) for e in ends) and _has_slab_partner(s, segs)):
                leaf = True
                break
        if leaf:
            dropped += 1
        else:
            kept.append(s)
    return kept, dropped


def drop_leaf_walls(walls, door_arcs):
    """After pairing: a wall one door-width long that starts at a hinge and runs along the
    hinge -> arc-end direction is an open door leaf drawn as a wall-thick slab (two wall-layer
    lines as far apart as a wall is thick), not a wall. walls: [(x1,y1,x2,y2,t)] m."""
    swings = [a for a in door_arcs if 80.0 <= a[3] <= 100.0 and 0.5 <= a[2] <= 1.3]
    if not swings:
        return walls, 0
    kept, dropped = [], 0
    for w in walls:
        L = math.hypot(w[2] - w[0], w[3] - w[1])
        leaf = False
        for a in swings:
            if not 0.75 * a[2] <= L <= 1.25 * a[2]:
                continue
            hinge = (a[0], a[1])
            for p, q in (((w[0], w[1]), (w[2], w[3])), ((w[2], w[3]), (w[0], w[1]))):
                if math.hypot(p[0] - hinge[0], p[1] - hinge[1]) > 0.15:
                    continue
                for e in ((a[4], a[5]), (a[6], a[7])):
                    ex, ey = e[0] - hinge[0], e[1] - hinge[1]
                    en = math.hypot(ex, ey)
                    cos = ((q[0] - p[0]) * ex + (q[1] - p[1]) * ey) / (L * en) if en else 0
                    if cos >= math.cos(math.radians(12.0)):
                        leaf = True
            if leaf:
                break
        if leaf:
            dropped += 1
        else:
            kept.append(w)
    return kept, dropped
