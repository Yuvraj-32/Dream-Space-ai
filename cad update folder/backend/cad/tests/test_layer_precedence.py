"""When a layer is *named* for walls, does it outrank wall-like geometry elsewhere?

Only when the named layer really holds walls. The gazebo sample's "0" is stone
hatching inside real, named walls (named layer wins). The NITIN BHAI sample has
a layer called "Wall" with no wall pairs at all, while its real walls sit on
"0"/"0. GF" (geometry must win, or nothing is detected).
"""
import ezdxf

from cad.detect import detect_file
from cad.pipeline import inspect_file

WALL_T = 230  # mm


def _rect(msp, x0, y0, x1, y1, layer):
    msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": layer})


def _house(msp, layer):
    """10 x 8 m, double-line outer walls and one double-line partition (two rooms)."""
    _rect(msp, 0, 0, 10000, 8000, layer)
    _rect(msp, WALL_T, WALL_T, 10000 - WALL_T, 8000 - WALL_T, layer)
    for x in (5000 - WALL_T / 2, 5000 + WALL_T / 2):
        msp.add_line((x, WALL_T), (x, 8000 - WALL_T), dxfattribs={"layer": layer})


def _roles(result):
    return {l["name"]: l["suggested_role"] for l in result["layers"]}


def test_named_wall_layer_without_walls_does_not_hide_real_walls(tmp_path):
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    _house(msp, "0")
    # A layer called "Wall" holding a few far-apart single lines: no wall pairs.
    for y in (1500, 3500, 5500):
        msp.add_line((1000, y), (4000, y), dxfattribs={"layer": "Wall"})
    for text, x in (("BEDROOM", 2000), ("KITCHEN", 7000)):
        msp.add_text(text, height=250, dxfattribs={"layer": "TEXT"}).set_placement((x, 4000))
    # A sofa drawn as nested outlines (back cushion 200 mm in): parallel, wall-like — not walls.
    _rect(msp, 6000, 1000, 9000, 2000, "SOFA")
    _rect(msp, 6200, 1200, 8800, 1800, "SOFA")
    path = str(tmp_path / "misnamed.dxf")
    doc.saveas(path)

    insp = inspect_file(path, str(tmp_path / "cache"))
    assert _roles(insp)["0"] == "wall"
    assert _roles(insp)["SOFA"] == "ignore"
    det = detect_file(path, str(tmp_path / "cache"))
    assert det["stats"]["walls_final"] >= 4
    assert det["stats"]["rooms_detected"] == 2


def test_named_wall_layer_with_walls_still_outranks_lookalike_geometry(tmp_path):
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    _house(msp, "A-WALL")
    # Stone-hatch look-alike on "0": many parallel lines 150 mm apart inside the rooms.
    for i in range(40):
        y = 600 + i * 150
        msp.add_line((600, y), (4400, y), dxfattribs={"layer": "0"})
    path = str(tmp_path / "hatched.dxf")
    doc.saveas(path)

    roles = _roles(inspect_file(path, str(tmp_path / "cache")))
    assert roles["A-WALL"] == "wall"
    assert roles["0"] == "ignore"
