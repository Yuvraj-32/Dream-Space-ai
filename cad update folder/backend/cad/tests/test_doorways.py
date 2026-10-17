"""A door is always on a wall that runs along its doorway; no floating or leaf-aligned doors."""
import math
import os

import pytest

from cad.converter import find_dwg2dxf
from cad.openings import attach_indices, find_openings

T = 0.15
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), *[".."] * 4))


def _arc(cx, cy, r, a0_deg):
    a0, a1 = math.radians(a0_deg), math.radians(a0_deg + 90)
    return (cx, cy, r, 90.0, cx + r * math.cos(a0), cy + r * math.sin(a0), cx + r * math.cos(a1), cy + r * math.sin(a1))


def test_door_between_two_walls_gets_a_wall_along_its_doorway():
    # Two parallel walls 1 m apart and no wall across: a door hinged on the left wall, open leaf
    # standing along that wall, closed position across to the right wall.
    walls = [(0, 0, 0, 5, T), (1.0, 0, 1.0, 5, T)]
    arc = _arc(0.0, 2.0, 0.9, 0)                               # ends (0.9, 2) across, (0, 2.9) along the left wall
    out, openings = find_openings(walls, [arc], [], [], [])
    openings = attach_indices(out, openings)
    assert len(openings) == 1
    wall = out[openings[0]["wall_index"]]
    assert abs(wall[1] - wall[3]) < 1e-6 and abs(wall[1] - 2.0) < 1e-6      # horizontal, at the hinge's height
    assert min(wall[0], wall[2]) <= 0.05 and max(wall[0], wall[2]) >= 0.85   # spans the doorway
    assert openings[0]["width"] == pytest.approx(0.9)


def test_door_whose_chord_lies_in_a_wall_gap_is_not_given_an_extra_wall():
    walls = [(0, 0, 3, 0, T), (3.9, 0, 8, 0, T)]
    out, openings = find_openings(walls, [_arc(3.0, 0, 0.9, 0)], [], [], [])
    assert len(out) == 1 and len(openings) == 1


def test_two_doors_on_different_walls_are_not_merged():
    walls = [(0, 0, 0, 5, T), (0, 2.6, 6, 2.6, T)]
    arcs = [_arc(0.0, 1.0, 0.9, 0), _arc(0.4, 2.6, 0.9, 270)]
    _, openings = find_openings(walls, arcs, [], [], [])
    assert len([o for o in openings if o["type"] == "door"]) == 2


PLANS = {
    "Big-House-Patio-Terrace.dwg": None,
    "Simple-Country-house-1806201-VER04.dwg": None,
    "Ishverbhai Punna.dwg": None,
    "Small-country-house-with-gazebo-1005201.dwg": None,
}


@pytest.mark.skipif(find_dwg2dxf() is None, reason="LibreDWG not installed")
@pytest.mark.parametrize("name", list(PLANS))
def test_no_floating_doors_in_real_plans(name, tmp_path):
    path = os.path.join(ROOT, name)
    if not os.path.isfile(path):
        pytest.skip(f"{name} not in the project folder")
    from cad.detect import detect_file
    from cad.pipeline import inspect_file
    result = detect_file(path, str(tmp_path / "cache"))
    walls = {w["id"]: w for w in result["walls"]}
    assert result["openings"]
    for o in result["openings"]:
        w = walls[o["wall_id"]]
        dx, dy = w["x2"] - w["x1"], w["y2"] - w["y1"]
        l2 = dx * dx + dy * dy
        u = max(0.0, min(1.0, ((o["x"] - w["x1"]) * dx + (o["y"] - w["y1"]) * dy) / l2)) if l2 else 0.0
        dist_px = math.hypot(o["x"] - (w["x1"] + u * dx), o["y"] - (w["y1"] + u * dy))
        # a door/window centre must lie on its wall: within the wall's half-thickness (+ a little)
        assert dist_px <= w["thickness"] / 2.0 + 3.0, f"{name}: {o['type']} {o['id']} floats {dist_px:.1f}px off its wall"
