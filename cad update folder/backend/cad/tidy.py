"""Final wall clean-up, run after doors/windows are placed. Metres, Y up.

Walls come from pairing parallel faces, so anything drawn as parallel lines
can become a wall. Audit of the eight test plans found four recurring errors:

  1. fixtures: toilet pans, cabinet boxes, lift cores -> small closed boxes of
     3+ short wall pieces (<= 1 m across)
  2. stair blobs: treads pair into one ~0.6 m "wall" a metre long
  3. stubs: door-jamb nubs and column returns, a <= 0.5 m piece hanging off a
     longer wall with a free end
  4. open corners: a wall that stops 0.05-0.6 m short of the perpendicular wall
     it meets; extended onto it so rooms close and 3D has no notch

Never touches a wall that carries a door or window, and never closes a corner
that has an opening next to it (that is a doorway, not a gap).
"""
import math

FIXTURE_MAX_M, FIXTURE_MAX_LEN, FIXTURE_MIN_PIECES = 1.0, 4.5, 3
BLOB_MIN_T, BLOB_MAX_LEN = 0.45, 2.0
STUB_MAX = 0.5
CORNER_MIN, CORNER_MAX = 0.05, 0.6
OPENING_CLEAR = 1.0


def _len(w):
    return math.hypot(w[2] - w[0], w[3] - w[1])


def _dist(px, py, w):
    dx, dy = w[2] - w[0], w[3] - w[1]
    l2 = dx * dx + dy * dy
    u = max(0.0, min(1.0, ((px - w[0]) * dx + (py - w[1]) * dy) / l2)) if l2 else 0.0
    return math.hypot(px - (w[0] + u * dx), py - (w[1] + u * dy))


def _touch(a, b, slack=0.08):
    reach = (a[4] + b[4]) / 2.0 + slack
    return (_dist(a[0], a[1], b) <= reach or _dist(a[2], a[3], b) <= reach
            or _dist(b[0], b[1], a) <= reach or _dist(b[2], b[3], a) <= reach)


def _carries_opening(w, openings):
    return any(_dist(o["x"], o["y"], w) <= w[4] / 2.0 + 0.2 for o in openings)


def _components(walls):
    parent = list(range(len(walls)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(walls)):
        for j in range(i + 1, len(walls)):
            if _touch(walls[i], walls[j]):
                parent[root(i)] = root(j)
    groups = {}
    for i in range(len(walls)):
        groups.setdefault(root(i), []).append(i)
    return list(groups.values())


def drop_fixtures_and_blobs(walls, openings):
    drop = set()
    for ids in _components(walls):
        xs = [v for i in ids for v in (walls[i][0], walls[i][2])]
        ys = [v for i in ids for v in (walls[i][1], walls[i][3])]
        extent = max(max(xs) - min(xs), max(ys) - min(ys))
        total = sum(_len(walls[i]) for i in ids)
        if (len(ids) >= FIXTURE_MIN_PIECES and extent <= FIXTURE_MAX_M and total <= FIXTURE_MAX_LEN
                and not any(_carries_opening(walls[i], openings) for i in ids)):
            drop.update(ids)
    for i, w in enumerate(walls):
        if w[4] > BLOB_MIN_T and _len(w) <= BLOB_MAX_LEN and not _carries_opening(w, openings):
            drop.add(i)
    return [w for i, w in enumerate(walls) if i not in drop], len(drop)


def drop_stubs(walls, openings):
    """A short piece with one free end and one end on another wall."""
    drop = set()
    for i, w in enumerate(walls):
        if _len(w) > STUB_MAX or _carries_opening(w, openings):
            continue
        ends = [(w[0], w[1]), (w[2], w[3])]
        touching = [any(_dist(p[0], p[1], o) <= (w[4] + o[4]) / 2.0 + 0.08
                        for j, o in enumerate(walls) if j != i) for p in ends]
        if touching.count(True) == 1:
            drop.add(i)
    return [w for i, w in enumerate(walls) if i not in drop], len(drop)


def close_corners(walls, openings):
    """Extend a free wall end onto the perpendicular wall it stops just short of."""
    walls = [list(w) for w in walls]
    closed = 0
    for i, w in enumerate(walls):
        L = _len(w)
        ux, uy = (w[2] - w[0]) / L, (w[3] - w[1]) / L
        for end in (0, 1):
            px, py = (w[0], w[1]) if end == 0 else (w[2], w[3])
            dx, dy = (-ux, -uy) if end == 0 else (ux, uy)
            if any(j != i and _dist(px, py, o) <= (w[4] + o[4]) / 2.0 + 0.08 for j, o in enumerate(walls)):
                continue                                   # already joined
            if any(math.hypot(px - o["x"], py - o["y"]) < OPENING_CLEAR for o in openings):
                continue                                   # a doorway, not a gap
            best = None
            for j, v in enumerate(walls):
                if j == i:
                    continue
                Lv = _len(v)
                vx, vy = (v[2] - v[0]) / Lv, (v[3] - v[1]) / Lv
                denom = dx * vy - dy * vx
                if abs(denom) < math.sin(math.radians(60.0)):    # a real crossing, not a near-parallel wall
                    continue
                s = ((v[0] - px) * vy - (v[1] - py) * vx) / denom
                u = ((v[0] - px) * dy - (v[1] - py) * dx) / denom
                margin = v[4] / 2.0 + 0.1
                if CORNER_MIN <= s <= CORNER_MAX and -margin <= u <= Lv + margin:
                    if best is None or s < best[0]:
                        best = (s, px + dx * s, py + dy * s)
            if best is not None:
                if end == 0:
                    w[0], w[1] = best[1], best[2]
                else:
                    w[2], w[3] = best[1], best[2]
                L = _len(w)
                ux, uy = (w[2] - w[0]) / L, (w[3] - w[1]) / L
                closed += 1
    return [tuple(w) for w in walls], closed


def tidy_walls(walls, openings):
    """Returns (walls, stats)."""
    walls, fixtures = drop_fixtures_and_blobs(walls, openings)
    walls, stubs = drop_stubs(walls, openings)
    walls, corners = close_corners(walls, openings)
    return walls, {"fixture_walls_dropped": fixtures, "stubs_dropped": stubs, "corners_closed": corners}
