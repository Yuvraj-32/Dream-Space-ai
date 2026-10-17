"""Recover a floor plan that exists in the file but was never placed in model space.

Phase 0/1 found THREE BEDROOM's whole plan (layers wall/door/window/stair, 124
labels) inside a block no INSERT references: LibreDWG decoded the objects that
would have placed it as "unknown" and dropped them, so model space only held
the dimensions. This looks for such unreferenced blocks that are plan-like
(many lines on wall layers plus door/window layers), and flattens them as extra
drawings placed far to the side of the real content so they cluster apart.

Only used when model space has no confident floor plan, so files that already
work are never touched. Block libraries are excluded by the plan-like test.
"""
import re

from .loader import Insert, Rec, _record_for

MIN_WALL_LINES = 40
GAP_M = 100.0               # clearance between the model content and each recovered block
_WALL = re.compile(r"wall|mur|pared", re.I)
_OPENING = re.compile(r"door|window|puert|ventan|glaz", re.I)


def plan_blocks(doc):
    """Names of unreferenced blocks that look like a floor plan, best first."""
    referenced = {e.dxf.name for e in doc.entitydb.values() if e.dxftype() == "INSERT"}
    found = []
    for block in doc.blocks:
        name = block.name
        if name.startswith("*") or name in referenced:
            continue
        wall = opening = 0
        for e in block:
            if e.dxftype() not in ("LINE", "LWPOLYLINE", "POLYLINE"):
                continue
            layer = e.dxf.get("layer", "0") or "0"
            if _WALL.search(layer):
                wall += 1
            elif _OPENING.search(layer):
                opening += 1
        if wall >= MIN_WALL_LINES and opening > 0:
            found.append((wall, name))
    return [name for _, name in sorted(found, reverse=True)]


def _shift(rec, dx, dy):
    b = rec.bbox
    rec.bbox = (b[0] + dx, b[1] + dy, b[2] + dx, b[3] + dy)
    if rec.segs:
        rec.segs = [(s[0] + dx, s[1] + dy, s[2] + dx, s[3] + dy) for s in rec.segs]
    if rec.arc:
        a = rec.arc
        rec.arc = (a[0] + dx, a[1] + dy, a[2], a[3], a[4] + dx, a[5] + dy, a[6] + dx, a[7] + dy)


def flatten_blocks(doc, names, records, metres_per_unit, base_top):
    """Append `names` blocks' content to `records` (shifted to the right of what is
    already there). Returns (new_inserts, {block_name: (start, end)})."""
    flat_tol = 0.02 / metres_per_unit
    xs = [r.bbox[2] for r in records if r.bbox]
    cursor = (max(xs) if xs else 0.0) + GAP_M / metres_per_unit
    inserts, spans = [], {}
    top = base_top

    for name in names:
        block = doc.blocks.get(name)
        start = len(records)
        local = []
        local_inserts = []

        def visit(e, parent_layer, owner, depth):
            layer = e.dxf.get("layer", "0") or "0"
            if layer == "0" and parent_layer:
                layer = parent_layer
            if e.dxftype() == "INSERT":
                if depth >= 3:
                    return
                try:
                    children = list(e.virtual_entities())
                except Exception:
                    return
                s = len(local)
                for child in children:
                    visit(child, layer, e.dxf.get("name", None), depth + 1)
                if len(local) > s:
                    local_inserts.append((e.dxf.get("name", "") or "", layer, s, len(local)))
                return
            rec = _record_for(e, layer, owner, top, flat_tol)
            if rec is not None:
                local.append(rec)

        for e in block:
            visit(e, None, None, 0)
        if not local:
            continue
        x0 = min(r.bbox[0] for r in local)
        y0 = min(r.bbox[1] for r in local)
        dx, dy = cursor - x0, -y0
        for r in local:
            _shift(r, dx, dy)
        records.extend(local)
        for n, layer, s, e_ in local_inserts:
            inserts.append(Insert(n, layer, top, start + s, start + e_))
        spans[name] = (start, len(records))
        cursor = max(r.bbox[2] for r in local) + GAP_M / metres_per_unit   # bboxes are already shifted
        top += 1
    return inserts, spans
