"""Read a DXF with ezdxf and flatten it into lightweight records.

Each record carries only what later stages need (effective layer, entity type,
2D bbox, line segments, text, arc info), so layers/clusters/thumbnails never
walk the ezdxf document again. Block references (INSERT) are expanded
recursively: content drawn on layer "0" inside a block inherits the INSERT's
layer, which is how AutoCAD itself displays it.
"""
import logging
import math

# ezdxf logs a warning per unsupported sub-object (e.g. "copy process ignored
# FIELD") while expanding blocks — thousands of lines, none actionable here.
logging.getLogger("ezdxf").setLevel(logging.ERROR)

MAX_RECORDS = 600_000
MAX_BLOCK_DEPTH = 4

_UNIT_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0, 7: 1000.0, 10: 0.9144, 14: 0.1}
_UNIT_NAME = {1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m", 7: "km", 10: "yd", 14: "dm"}
NAME_TO_M = {"mm": 0.001, "cm": 0.01, "m": 1.0, "in": 0.0254, "ft": 0.3048}

_PATH_KINDS = {"LWPOLYLINE", "POLYLINE", "ARC", "CIRCLE", "ELLIPSE", "SPLINE"}


class Rec:
    __slots__ = ("layer", "kind", "block", "bbox", "segs", "text", "arc", "top")

    def __init__(self, layer, kind, block, bbox, segs=None, text=None, arc=None, top=-1):
        self.layer, self.kind, self.block, self.bbox = layer, kind, block, bbox
        self.segs, self.text, self.arc, self.top = segs, text, arc, top

    @property
    def center(self):
        b = self.bbox
        return ((b[0] + b[2]) / 2.0, (b[1] + b[3]) / 2.0)


def load_doc(dxf_path):
    """Normal reader first (~2x faster); the tolerant `recover` reader only if
    the DXF is malformed (possible with converter output)."""
    import ezdxf
    from ezdxf import recover
    try:
        return ezdxf.readfile(dxf_path), {"reader": "standard", "audit_errors": 0, "audit_fixes": 0}
    except Exception:
        doc, auditor = recover.readfile(dxf_path)
        return doc, {"reader": "recover", "audit_errors": len(auditor.errors),
                     "audit_fixes": len(auditor.fixes)}


def header_units(doc):
    """(code, name, metres_per_unit) from $INSUNITS; name is None if unitless/unknown."""
    code = int(doc.header.get("$INSUNITS", 0) or 0)
    return code, _UNIT_NAME.get(code), _UNIT_M.get(code)


def _bbox_of_points(pts):
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys))


def _segments_from_points(pts, closed=False):
    segs = [(pts[i][0], pts[i][1], pts[i + 1][0], pts[i + 1][1]) for i in range(len(pts) - 1)]
    if closed and len(pts) > 2:
        segs.append((pts[-1][0], pts[-1][1], pts[0][0], pts[0][1]))
    return segs


def _fast_bbox(e):
    from ezdxf import bbox as ezbbox
    try:
        box = ezbbox.extents([e], fast=True)
    except Exception:
        return None
    if not box.has_data:
        return None
    return (box.extmin.x, box.extmin.y, box.extmax.x, box.extmax.y)


def _record_for(e, layer, block, top, flat_tol):
    """One flattened record for a non-INSERT entity, or None to skip."""
    from ezdxf import path as ezpath

    kind = e.dxftype()
    if kind == "LINE":
        s, t = e.dxf.start, e.dxf.end
        seg = (s.x, s.y, t.x, t.y)
        return Rec(layer, kind, block, _bbox_of_points([(s.x, s.y), (t.x, t.y)]), segs=[seg], top=top)

    if kind in _PATH_KINDS:
        try:
            pts = [(v.x, v.y) for v in ezpath.make_path(e).flattening(flat_tol)]
        except Exception:
            return None
        if len(pts) < 2:
            return None
        arc = None
        if kind == "ARC":
            sweep = (e.dxf.end_angle - e.dxf.start_angle) % 360.0
            c = e.dxf.center
            arc = (c.x, c.y, float(e.dxf.radius), sweep)
        return Rec(layer, kind, block, _bbox_of_points(pts), segs=_segments_from_points(pts), arc=arc, top=top)

    if kind in ("TEXT", "MTEXT"):
        try:
            text = e.dxf.text if kind == "TEXT" else e.plain_text()
            p = e.dxf.insert
        except Exception:
            return None
        text = " ".join((text or "").split())
        if not text:
            return None
        return Rec(layer, kind, block, (p.x, p.y, p.x, p.y), text=text, top=top)

    if kind == "DIMENSION":
        pts = []
        for attr in ("defpoint", "defpoint2", "defpoint3", "text_midpoint"):
            if e.dxf.hasattr(attr):
                v = e.dxf.get(attr)
                pts.append((v.x, v.y))
        return Rec(layer, kind, block, _bbox_of_points(pts), top=top) if pts else None

    box = _fast_bbox(e)
    return Rec(layer, kind, block, box, top=top) if box else None


def flatten(doc, metres_per_unit):
    """Model space -> list[Rec]. Returns (records, stats)."""
    flat_tol = 0.02 / metres_per_unit  # ~2 cm chord error when approximating curves
    records = []
    stats = {"top_level_entities": 0, "block_refs_expanded": 0, "truncated": False}

    def visit(entity, parent_layer, block, top, depth):
        if len(records) >= MAX_RECORDS:
            stats["truncated"] = True
            return
        layer = entity.dxf.get("layer", "0") or "0"
        if layer == "0" and parent_layer:
            layer = parent_layer
        if entity.dxftype() == "INSERT":
            if depth >= MAX_BLOCK_DEPTH:
                return
            stats["block_refs_expanded"] += 1
            try:
                children = list(entity.virtual_entities())
            except Exception:
                return
            name = entity.dxf.get("name", None)
            for child in children:
                visit(child, layer, name, top, depth + 1)
            return
        rec = _record_for(entity, layer, block, top, flat_tol)
        if rec is not None:
            records.append(rec)

    for idx, e in enumerate(doc.modelspace()):
        stats["top_level_entities"] += 1
        visit(e, None, None, idx, 0)
        if stats["truncated"]:
            break
    stats["records"] = len(records)
    return records, stats


def seg_length(s):
    return math.hypot(s[2] - s[0], s[3] - s[1])
