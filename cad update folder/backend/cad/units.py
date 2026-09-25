"""Decide the drawing's real units from its geometry, not just the header.

Phase 1 testing found the $INSUNITS header wrong in 3 of 7 samples (a house
drawn in metres labelled "mm", one drawn in mm labelled "inches"). Each
candidate unit is scored on evidence that only lines up at the true scale:
  - walls: parallel line pairs 75–450 mm apart,
  - doors: ~90° swing arcs with a 0.5–1.3 m radius,
  - size: the drawing's core extent is a plausible real-world size.
The header unit gets a small prior so it wins ties.
"""
from .layers import paired_fraction, _is_door_arc
from .loader import NAME_TO_M

CANDIDATES = ("mm", "cm", "m", "in", "ft")
_HEADER_PRIOR = 0.15
_MAX_SEGS = 40_000


def _core_extent(records):
    xs = sorted(r.center[0] for r in records if r.bbox)
    ys = sorted(r.center[1] for r in records if r.bbox)
    if not xs:
        return 0.0
    lo, hi = int(len(xs) * 0.05), max(0, int(len(xs) * 0.95) - 1)
    return max(xs[hi] - xs[lo], ys[hi] - ys[lo])


def resolve_units(records, header_name):
    """Return {"name", "metres_per_unit", "confidence", "header", "evidence"}.
    confidence: "header" (header confirmed), "corrected" (header overridden
    by geometry), or "guess" (no header, picked from geometry)."""
    segs = []
    for r in records:
        if r.segs:
            segs.extend(r.segs)
            if len(segs) >= _MAX_SEGS:
                break
    arcs = [r.arc for r in records if r.arc]
    extent = _core_extent(records)

    evidence = {}
    for name in CANDIDATES:
        mpu = NAME_TO_M[name]
        _, axis_len, paired_len = paired_fraction(segs, mpu)
        pair = paired_len / axis_len if axis_len else 0.0
        doors = sum(1 for a in arcs if _is_door_arc(a, mpu))
        size_m = extent * mpu
        size_ok = 3.0 <= size_m <= 1000.0
        score = pair + 0.4 * min(1.0, doors / 3.0) + (0.2 if size_ok else -0.5)
        if name == header_name:
            score += _HEADER_PRIOR
        evidence[name] = {"score": round(score, 3), "pair_frac": round(pair, 2),
                          "door_arcs": doors, "core_size_m": round(size_m, 1)}

    best = max(CANDIDATES, key=lambda n: evidence[n]["score"])
    if header_name is None:
        confidence = "guess"
    elif best == header_name:
        confidence = "header"
    else:
        confidence = "corrected"
    return {"name": best, "metres_per_unit": NAME_TO_M[best], "confidence": confidence,
            "header": header_name, "evidence": evidence}
