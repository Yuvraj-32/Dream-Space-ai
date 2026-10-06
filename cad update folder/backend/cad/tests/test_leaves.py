"""Open door leaves must not become walls; the door belongs in the wall gap."""
import math

import ezdxf
import pytest

from cad.detect import detect_file
from cad.leaves import drop_door_leaves, drop_leaf_walls

T = 0.15


def _arc(cx, cy, r, a0_deg):
    a0, a1 = math.radians(a0_deg), math.radians(a0_deg + 90)
    return (cx, cy, r, 90.0, cx + r * math.cos(a0), cy + r * math.sin(a0), cx + r * math.cos(a1), cy + r * math.sin(a1))


def test_exact_leaf_line_is_dropped_but_a_long_wall_is_not():
    arc = _arc(3.0, 0, 0.9, 0)                                  # hinge (3,0); ends (3.9,0) and (3,0.9)
    segs = [(3.0, 0.0, 3.9, 0.0),                               # closed leaf: hinge -> end, one radius
            (3.0, 0.0, 3.0, 0.9),                               # open leaf
            (3.0, 0.0, 9.0, 0.0)]                               # a real wall face running on from the hinge
    kept, n = drop_door_leaves(segs, [arc])
    assert n == 2 and kept == [(3.0, 0.0, 9.0, 0.0)]


def test_thin_double_line_slab_leaf_is_dropped_but_wall_faces_are_not():
    arc = _arc(3.0, 0, 0.9, 0)
    slab = [(3.0, 0.1, 3.0, 0.95), (3.04, 0.1, 3.04, 0.95)]    # 4 cm apart, starts 0.1 past the hinge
    face = [(3.0, 0.5, 3.0, 1.35), (3.15, 0.5, 3.15, 1.35)]    # 15 cm apart: a wall, not a slab
    kept, n = drop_door_leaves(slab + face, [arc])
    assert n == 2 and kept == face


def test_wall_thick_leaf_slab_is_dropped_after_pairing_but_a_long_wall_is_not():
    arc = _arc(5.15, 8.22, 0.87, 270)                          # hinge at the top of a vertical leaf
    leaf_wall = (5.23, 8.2, 5.23, 7.35, T)                     # one door-width long, starts at the hinge, runs along it
    long_wall = (5.23, 8.2, 5.23, 3.0, T)                      # same start, far longer: a real wall
    kept, n = drop_leaf_walls([leaf_wall, long_wall], [arc])
    assert n == 1 and kept == [long_wall]


def test_open_door_is_placed_in_the_wall_gap_not_on_its_leaf(tmp_path):
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    wall = {"layer": "A-WALL"}
    # East-west wall 10 m long with a 0.9 m door gap (x 4.0-4.9), double line 150 mm thick.
    for (x1, y1, x2, y2) in [(0, 0, 4000, 0), (0, 150, 4000, 150), (4900, 0, 10000, 0), (4900, 150, 10000, 150)]:
        msp.add_line((x1 / 1000, y1 / 1000), (x2 / 1000, y2 / 1000), dxfattribs=wall)
    # The rest of a house so the file is a plan: three more walls, labels.
    for (x1, y1, x2, y2) in [(0, 6000, 10000, 6000), (0, 5850, 10000, 5850), (0, 0, 0, 6000), (150, 150, 150, 5850),
                             (10000, 0, 10000, 6000), (9850, 150, 9850, 5850), (5000, 150, 5000, 3000), (5150, 150, 5150, 3000)]:
        msp.add_line((x1 / 1000, y1 / 1000), (x2 / 1000, y2 / 1000), dxfattribs=wall)
    # Door hinged at the east jamb (4.9, 0.15): closed along the wall to the west, open leaf standing in
    # the room, drawn as TWO WALL-LAYER lines 0.15 apart (a wall-thick slab) starting a little past the hinge.
    msp.add_arc((4.9, 0.075), 0.9, 90, 180, dxfattribs={"layer": "DOOR"})
    msp.add_line((4.9, 0.2), (4.9, 1.05), dxfattribs=wall)
    msp.add_line((5.05, 0.1), (5.05, 0.95), dxfattribs=wall)
    msp.add_text("BEDROOM", height=0.25, dxfattribs={"layer": "TEXT"}).set_placement((2.0, 3.0))
    doc.saveas(str(tmp_path / "open_door.dxf"))
    result = detect_file(str(tmp_path / "open_door.dxf"), str(tmp_path / "cache"), cluster_id="c0")
    walls = {w["id"]: w for w in result["walls"]}
    doors = [o for o in result["openings"] if o["type"] == "door"]
    assert len(doors) == 1
    door_wall = walls[doors[0]["wall_id"]]
    assert abs(door_wall["y1"] - door_wall["y2"]) < 3                     # on the east-west wall, not on the leaf
    assert doors[0]["width_m"] == pytest.approx(0.9, abs=0.1)
    assert not any(abs(w["x1"] - w["x2"]) < 3 and 0.6 <= w["length_ft"] * 0.3048 <= 1.2 for w in result["walls"])
