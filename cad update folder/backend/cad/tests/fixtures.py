"""Synthetic DXF drawings built with ezdxf for tests (nothing binary is committed).

All geometry is authored in millimetres and multiplied by `s` so the same
drawing can be written in other units (e.g. s=0.001 for metres).
"""
import ezdxf

WALL_T = 200  # mm


def _rect(msp, x0, y0, x1, y1, layer, s):
    msp.add_lwpolyline([(x0 * s, y0 * s), (x1 * s, y0 * s), (x1 * s, y1 * s), (x0 * s, y1 * s)],
                       close=True, dxfattribs={"layer": layer})


def _text(msp, text, x, y, layer, s, height=250):
    msp.add_text(text, height=height * s, dxfattribs={"layer": layer}).set_placement((x * s, y * s))


def _door_block(doc, s):
    name = f"DOOR_900_{int(s * 1e6)}"
    if name not in doc.blocks:
        blk = doc.blocks.new(name)
        # Drawn on layer "0" so it inherits the INSERT's layer, like real door blocks.
        blk.add_arc((0, 0), 900 * s, 0, 90, dxfattribs={"layer": "0"})
        blk.add_line((0, 0), (900 * s, 0), dxfattribs={"layer": "0"})
    return name


def add_plan(doc, ox=0, oy=0, s=1.0, labels=("BEDROOM", "KITCHEN")):
    """10 m x 8 m house: double-line outer walls, one double-line partition,
    a door block, room labels, a piece of furniture."""
    msp = doc.modelspace()
    x0, y0, x1, y1 = ox, oy, ox + 10000, oy + 8000
    _rect(msp, x0, y0, x1, y1, "A-WALL", s)
    _rect(msp, x0 + WALL_T, y0 + WALL_T, x1 - WALL_T, y1 - WALL_T, "A-WALL", s)
    cx = ox + 5000
    for x in (cx - WALL_T / 2, cx + WALL_T / 2):
        msp.add_line((x * s, (y0 + WALL_T) * s), (x * s, (y1 - WALL_T) * s), dxfattribs={"layer": "A-WALL"})
    msp.add_blockref(_door_block(doc, s), (cx * s, (oy + 3000) * s), dxfattribs={"layer": "DOOR"})
    _text(msp, labels[0], ox + 2000, oy + 4000, "TEXT", s)
    _text(msp, labels[1], ox + 7000, oy + 4000, "TEXT", s)
    _rect(msp, ox + 1000, oy + 1000, ox + 3000, oy + 2500, "FURNITURE", s)


def add_elevation(doc, ox=0, oy=0, s=1.0):
    """Front elevation: wall outline, windows, and a pitched roof (long diagonals)."""
    msp = doc.modelspace()
    _rect(msp, ox, oy, ox + 10000, oy + 3000, "ELEVATION", s)
    for wx in (1000, 4000, 7000):
        _rect(msp, ox + wx, oy + 1000, ox + wx + 1500, oy + 2200, "ELEVATION", s)
    for a, b in (((ox - 500, oy + 3000), (ox + 5000, oy + 5500)),
                 ((ox + 5000, oy + 5500), (ox + 10500, oy + 3000))):
        msp.add_line((a[0] * s, a[1] * s), (b[0] * s, b[1] * s), dxfattribs={"layer": "ELEVATION"})


def write_simple_plan(path, units=4, s=1.0):
    doc = ezdxf.new("R2010", units=units)
    add_plan(doc, s=s)
    doc.saveas(path)
    return path


def write_sheet(path):
    """Two plans side by side + an elevation + title block, all inside a frame,
    plus a stray point far away (the Phase 0 'outlier extents' case)."""
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    add_plan(doc, 0, 0)
    add_plan(doc, 15000, 0, labels=("LIVING ROOM", "DINING ROOM"))
    add_elevation(doc, 0, -9000)
    _rect(msp, 18000, -9000, 25000, -6000, "TITLE", 1.0)
    for y in (-8000, -7000):
        msp.add_line((18000, y), (25000, y), dxfattribs={"layer": "TITLE"})
    _text(msp, "PROJECT: TEST HOUSE", 18200, -6500, "TITLE", 1.0)
    _rect(msp, -3000, -12000, 28000, 11000, "BORDER", 1.0)
    msp.add_point((5e7, 5e7), dxfattribs={"layer": "0"})
    doc.saveas(path)
    return path


def write_labels_only(path):
    """Room names and nothing else — like the Phase 1 plan whose walls LibreDWG dropped."""
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    for text, x, y in (("MASTER BEDROOM", 0, 0), ("KITCHEN", 4000, 0), ("BATH", 0, 3000), ("LOUNGE", 4000, 3000)):
        _text(msp, text, x, y, "TEXT", 1.0)
    add_elevation(doc, 20000, 0)
    doc.saveas(path)
    return path


def write_empty(path):
    ezdxf.new("R2010", units=4).saveas(path)
    return path
