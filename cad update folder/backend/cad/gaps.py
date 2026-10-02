"""Window gaps: wall pieces cut where a window sits, bridged and given a window opening.

walls.py draws a wall from its two faces; where a window interrupts the wall
the faces stop, leaving a gap between two collinear wall pieces. 3D then shows
a hole to the floor and no window. A gap is a window when the drawing puts
glazing lines inside it: lines running along the wall, within the wall's band,
across most of the gap. (Door gaps are handled in openings.py via swing arcs;
gaps with no such lines stay open passages.)

Pure additions: nothing here changes wall pairing or door detection.
"""
import math

MIN_GAP, MAX_GAP = 0.35, 4.0      # m between two wall ends
BAND_SLACK = 0.06                 # evidence lines may sit this far outside the wall band
MIN_COVER = 0.6                   # share of the gap the evidence lines must span
PARALLEL_TOL = math.sin(math.radians(3.0))


def _frame(w):
    dx, dy = w[2] - w[0], w[3] - w[1]
    L = math.hypot(dx, dy)
    return L, dx / L, dy / L


def find_gaps(walls):
    """Collinear gaps between two wall pieces: [(i, end_i, j, end_j, length)]."""
    gaps = []
    for i, a in enumerate(walls):
        La, ux, uy = _frame(a)
        for ei, (px, py) in enumerate(((a[0], a[1]), (a[2], a[3]))):
            sgn = -1.0 if ei == 0 else 1.0           # outward direction of this end along a
            best = None
            for j, b in enumerate(walls):
                if j == i:
                    continue
                Lb, vx, vy = _frame(b)
                if abs(ux * vy - uy * vx) > PARALLEL_TOL:
                    continue
                nx, ny = -uy, ux
                if abs((b[0] - px) * nx + (b[1] - py) * ny) > 0.5 * min(a[4], b[4]) + 0.03:
                    continue                          # not the same wall line
                for ej, (qx, qy) in enumerate(((b[0], b[1]), (b[2], b[3]))):
                    d = ((qx - px) * ux + (qy - py) * uy) * sgn
                    if MIN_GAP <= d <= MAX_GAP and (best is None or d < best[0]):
                        best = (d, j, ej)
            if best is not None and (i, ei) < (best[1], best[2]):
                gaps.append((i, ei, best[1], best[2], best[0]))
    return gaps


def _evidence(gap_a, gap_b, thickness, segs):
    """Share of the gap spanned by `segs` lying along it within the wall band."""
    (ax, ay), (bx, by) = gap_a, gap_b
    L = math.hypot(bx - ax, by - ay)
    ux, uy = (bx - ax) / L, (by - ay) / L
    nx, ny = -uy, ux
    spans = []
    for s in segs:
        dx, dy = s[2] - s[0], s[3] - s[1]
        sl = math.hypot(dx, dy)
        if sl < 0.1 or abs(ux * dy - uy * dx) > PARALLEL_TOL * sl:
            continue
        off = ((s[0] + s[2]) / 2 - ax) * nx + ((s[1] + s[3]) / 2 - ay) * ny
        if abs(off) > thickness / 2 + BAND_SLACK:
            continue
        t1 = (s[0] - ax) * ux + (s[1] - ay) * uy
        t2 = (s[2] - ax) * ux + (s[3] - ay) * uy
        lo, hi = max(0.0, min(t1, t2)), min(L, max(t1, t2))
        if hi > lo:
            spans.append((lo, hi))
    spans.sort()
    covered, end = 0.0, 0.0
    for lo, hi in spans:
        lo = max(lo, end)
        if hi > lo:
            covered += hi - lo
            end = hi
    return covered / L, len(spans)


def window_gaps(walls, evidence_segs, taken_points=()):
    """Return [(wall_i, end_i, wall_j, end_j, centre_xy, width)] for gaps holding
    window evidence. `taken_points`: opening centres already placed (skip gaps that
    already carry a door/window)."""
    found = []
    for i, ei, j, ej, length in find_gaps(walls):
        a = walls[i]
        pa = (a[0], a[1]) if ei == 0 else (a[2], a[3])
        b = walls[j]
        pb = (b[0], b[1]) if ej == 0 else (b[2], b[3])
        centre = ((pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0)
        if any(math.hypot(centre[0] - tx, centre[1] - ty) < length / 2.0 for tx, ty in taken_points):
            continue
        cover, n = _evidence(pa, pb, max(a[4], b[4]), evidence_segs)
        found.append((i, ei, j, ej, centre, length, cover, n))
    return found


MIN_WINDOW_COVER = 0.85
LINES_RANGE = (2, 10)    # a window symbol is a few parallel lines; floor hatch has dozens


STUB_LEN, WIDE_GAP = 0.5, 1.5


def _stub_to_wide_gap(walls, gap):
    """A wide gap next to a tiny stub is a railing/balustrade post, not a window set
    in a wall (Ishverbhai's balcony: a 0.38 m stub, 3.2 m gap, 2 railing lines)."""
    i, _, j, _, _, length, _, _ = gap
    shortest = min(_frame(walls[i])[0], _frame(walls[j])[0])
    return shortest < STUB_LEN and length > WIDE_GAP


def bridge_windows(walls, evidence_segs, taken_points=()):
    """Close window gaps. Returns (walls, windows) — windows are
    {"type","x","y","width"} in metres; walls with a bridged gap become one wall."""
    accepted = [g for g in window_gaps(walls, evidence_segs, taken_points)
                if g[6] >= MIN_WINDOW_COVER and LINES_RANGE[0] <= g[7] <= LINES_RANGE[1]
                and not _stub_to_wide_gap(walls, g)]
    if not accepted:
        return walls, []

    parent = list(range(len(walls)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, _, j, _, *_ in accepted:
        parent[root(i)] = root(j)
    groups = {}
    for i in range(len(walls)):
        groups.setdefault(root(i), []).append(i)

    merged = []
    for members in groups.values():
        if len(members) == 1:
            merged.append(tuple(walls[members[0]]))
            continue
        base = walls[max(members, key=lambda k: _frame(walls[k])[0])]
        _, ux, uy = _frame(base)
        ts = [((p[0] - base[0]) * ux + (p[1] - base[1]) * uy)
              for k in members for p in ((walls[k][0], walls[k][1]), (walls[k][2], walls[k][3]))]
        lo, hi = min(ts), max(ts)
        thick = max(walls[k][4] for k in members)
        merged.append((base[0] + ux * lo, base[1] + uy * lo, base[0] + ux * hi, base[1] + uy * hi, thick))
    windows = [{"type": "window", "x": g[4][0], "y": g[4][1], "width": g[5]} for g in accepted]
    return merged, windows
