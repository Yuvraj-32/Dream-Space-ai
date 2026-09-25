"""Per-layer statistics and a suggested role for each layer.

Roles: wall, door, window, room_label, ignore. The suggestion combines the
layer name (CAD offices name layers inconsistently — Phase 0 found "A-WALL",
"WALLS", walls on "0", and files with no wall layer at all) with a geometry
signature: walls are drawn as pairs of parallel lines 75–450 mm apart, doors
as ~90° arcs. The user confirms/corrects roles in the review step.
"""
import collections
import math
import re

from .loader import seg_length
from .vocab import looks_like_room_label

ROLES = ("wall", "door", "window", "room_label", "ignore")

# Checked in this order; the first matching role wins. "ignore" goes first so
# names like "WALL ELEV." or "A-WALL-PATT" aren't mistaken for walls.
_NAME_RULES = [
    ("ignore", {
        "prefix": ("dim", "furn", "mobil", "muebl", "hatch", "patt", "grid", "axis", "axes",
                   "title", "border", "frame", "tree", "plant", "landsc", "elev", "section",
                   "roof", "plumb", "pipe", "manhole", "elec", "defpoint", "vport", "viewport",
                   "gulv", "tile", "sanit", "struct", "beam", "footing", "column", "site",
                   "contour", "parking", "note", "comment", "logo", "cota", "cotas",
                   "pilar", "bound", "plinth", "textur", "nota", "tarjeta", "coord", "equip"),
        "exact": ("fur", "pat", "rcc", "col", "dims", "ele"),
    }),
    ("wall", {"prefix": ("wall", "mur", "pared", "brick", "partit", "masonr", "blockwork"), "exact": ()}),
    ("door", {"prefix": ("door", "puert", "porte"), "exact": ("dr", "drs")}),
    ("window", {"prefix": ("window", "ventan", "glaz", "fenet"), "exact": ("win", "wdw", "wind")}),
    ("room_label", {"prefix": ("text", "room", "label", "name", "anno", "rotul"), "exact": ()}),
]

_TOKEN_RE = re.compile(r"[a-z0-9]+")

WALL_MIN_M, WALL_MAX_M = 0.075, 0.45
AXIS_TOL_DEG = 3.0
MAX_PAIR_SEGMENTS = 40_000


def _name_role(name):
    tokens = _TOKEN_RE.findall(name.lower())
    for role, rule in _NAME_RULES:
        for tok in tokens:
            if tok in rule["exact"] or tok.startswith(rule["prefix"]):
                return role, tok
    return None, None


def paired_fraction(segs, metres_per_unit, min_len_m=0.3):
    """How much axis-aligned line length has a parallel partner at a wall-like
    spacing. Returns (total_len, axis_len, paired_len) in drawing units."""
    lo = WALL_MIN_M / metres_per_unit
    hi = WALL_MAX_M / metres_per_unit
    min_len = min_len_m / metres_per_unit
    tol = math.tan(math.radians(AXIS_TOL_DEG))

    total = 0.0
    horiz, vert = [], []  # (offset, start, end, length)
    for s in segs[:MAX_PAIR_SEGMENTS]:
        dx, dy = s[2] - s[0], s[3] - s[1]
        length = math.hypot(dx, dy)
        total += length
        if length < min_len:
            continue
        if abs(dy) <= abs(dx) * tol:
            a, b = sorted((s[0], s[2]))
            horiz.append(((s[1] + s[3]) / 2.0, a, b, length))
        elif abs(dx) <= abs(dy) * tol:
            a, b = sorted((s[1], s[3]))
            vert.append(((s[0] + s[2]) / 2.0, a, b, length))

    axis_len = sum(h[3] for h in horiz) + sum(v[3] for v in vert)
    paired_len = 0.0
    for group in (horiz, vert):
        group.sort()
        paired = [False] * len(group)
        for i, (off_i, a_i, b_i, _) in enumerate(group):
            j = i + 1
            while j < len(group) and group[j][0] - off_i <= hi:
                off_j, a_j, b_j, _ = group[j]
                if off_j - off_i >= lo:
                    overlap = min(b_i, b_j) - max(a_i, a_j)
                    if overlap > 0.5 * min(b_i - a_i, b_j - a_j):
                        paired[i] = paired[j] = True
                j += 1
        paired_len += sum(g[3] for g, p in zip(group, paired) if p)
    return total, axis_len, paired_len


def _is_door_arc(arc, metres_per_unit):
    _, _, r, sweep = arc
    r_m = r * metres_per_unit
    return 80.0 <= sweep <= 100.0 and 0.5 <= r_m <= 1.3


def _layer_color(doc, name):
    from ezdxf import colors
    layer = doc.layers.get(name) if doc.layers.has_entry(name) else None
    if layer is None:
        return "#ffffff"
    rgb = layer.rgb
    if rgb is None:
        aci = abs(int(layer.color or 7))
        rgb = colors.aci2rgb(aci if 1 <= aci <= 255 else 7)
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _layer_visible(doc, name):
    if not doc.layers.has_entry(name):
        return True
    layer = doc.layers.get(name)
    return not (layer.is_off() or layer.is_frozen())


def analyze_layers(doc, records, metres_per_unit):
    """Return a list of layer dicts (sorted by entity count) with a suggested role."""
    by_layer = collections.defaultdict(list)
    for r in records:
        by_layer[r.layer].append(r)

    layers = []
    for name, recs in by_layer.items():
        kinds = collections.Counter(r.kind for r in recs)
        n = len(recs)
        segs = [s for r in recs if r.segs for s in r.segs]
        total, axis_len, paired_len = paired_fraction(segs, metres_per_unit)
        axis_frac = axis_len / total if total else 0.0
        pair_frac = paired_len / axis_len if axis_len else 0.0
        door_arcs = sum(1 for r in recs if r.arc and _is_door_arc(r.arc, metres_per_unit))
        texts = [r.text for r in recs if r.text]
        room_texts = sum(1 for t in texts if looks_like_room_label(t))
        total_m = total * metres_per_unit
        visible = _layer_visible(doc, name)

        role, conf, reason = _suggest_role(name, n, kinds, axis_frac, pair_frac, total_m,
                                           door_arcs, len(texts), room_texts, visible)
        layers.append({
            "name": name,
            "color": _layer_color(doc, name),
            "visible": visible,
            "entities": n,
            "types": dict(kinds.most_common(5)),
            "length_m": round(total_m, 1),
            "axis_frac": round(axis_frac, 2),
            "pair_frac": round(pair_frac, 2),
            "door_arcs": door_arcs,
            "texts": len(texts),
            "text_samples": list(dict.fromkeys(texts))[:3],
            "suggested_role": role,
            "confidence": conf,
            "reason": reason,
        })
    layers.sort(key=lambda l: l["entities"], reverse=True)
    return layers


def _suggest_role(name, n, kinds, axis_frac, pair_frac, total_m, door_arcs, n_texts, room_texts, visible):
    if not visible:
        return "ignore", 0.8, "layer is off/frozen in the drawing"

    name_role, token = _name_role(name)
    wall_geom = pair_frac >= 0.3 and axis_frac >= 0.55 and total_m >= 10.0

    if name_role == "wall":
        if wall_geom or pair_frac >= 0.15:
            return "wall", 0.95, f"name '{token}' + parallel wall lines"
        return "wall", 0.7, f"name '{token}'"
    if name_role in ("door", "window"):
        return name_role, 0.9, f"name '{token}'"
    if name_role == "room_label":
        return "room_label", (0.9 if n_texts else 0.6), f"name '{token}'"
    if name_role == "ignore":
        return "ignore", 0.85, f"name '{token}'"

    if n_texts and n_texts / n >= 0.5:
        return "room_label", (0.75 if room_texts >= 2 else 0.6), f"{n_texts} text labels"
    share = lambda k: kinds.get(k, 0) / n
    if share("DIMENSION") >= 0.5:
        return "ignore", 0.7, "mostly dimensions"
    if share("HATCH") >= 0.5:
        return "ignore", 0.6, "mostly hatch patterns"
    if wall_geom:
        conf = round(min(0.85, 0.45 + pair_frac * 0.5), 2)
        return "wall", conf, f"{int(pair_frac * 100)}% of lines in wall-like parallel pairs"
    if door_arcs >= 1 and n <= 600:
        return "door", 0.5, f"{door_arcs} door-swing arcs"
    return "ignore", 0.4, "no wall/door/text signature"
