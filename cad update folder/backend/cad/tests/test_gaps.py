"""Window-gap bridging: walls cut by a window symbol become one wall plus a window."""
import pytest

from cad.detect import detect_file
from cad.gaps import bridge_windows

T = 0.15


def _glazing(x0, x1, y, n=3):
    """n parallel window-symbol lines across a gap, within the wall band."""
    return [(x0, y + (k - (n - 1) / 2) * 0.04, x1, y + (k - (n - 1) / 2) * 0.04) for k in range(n)]


def test_window_gap_is_bridged_and_becomes_a_window():
    walls = [(0, 0, 3, 0, T), (4.2, 0, 8, 0, T)]               # 1.2 m gap between two pieces
    merged, windows = bridge_windows(walls, _glazing(3, 4.2, 0))
    assert len(merged) == 1 and merged[0][0] == pytest.approx(0) and merged[0][2] == pytest.approx(8)
    assert len(windows) == 1
    assert windows[0]["width"] == pytest.approx(1.2) and windows[0]["x"] == pytest.approx(3.6)


def test_gap_without_glazing_stays_open():
    walls = [(0, 0, 3, 0, T), (4.2, 0, 8, 0, T)]
    merged, windows = bridge_windows(walls, [])
    assert len(merged) == 2 and windows == []


def test_floor_hatch_is_not_a_window():
    walls = [(0, 0, 3, 0, T), (4.2, 0, 8, 0, T)]
    hatch = [(3, -0.05 + 0.005 * k, 4.2, -0.05 + 0.005 * k) for k in range(20)]
    assert bridge_windows(walls, hatch)[1] == []


def test_gap_already_holding_a_door_is_left_alone():
    walls = [(0, 0, 3, 0, T), (4.0, 0, 8, 0, T)]
    merged, windows = bridge_windows(walls, _glazing(3, 4, 0), taken_points=[(3.5, 0)])
    assert len(merged) == 2 and windows == []


def test_railing_post_is_not_a_window():
    # Ishverbhai's balcony: a 0.38 m stub, a 3.2 m gap and two railing lines.
    walls = [(0, 0, 6, 0, T), (9.2, 0, 9.58, 0, T)]
    assert bridge_windows(walls, _glazing(6, 9.2, 0, n=2))[1] == []


def test_two_windows_in_a_row_chain_into_one_wall():
    walls = [(0, 0, 2, 0, T), (3, 0, 5, 0, T), (6, 0, 8, 0, T)]
    ev = _glazing(2, 3, 0) + _glazing(5, 6, 0)
    merged, windows = bridge_windows(walls, ev)
    assert len(merged) == 1 and len(windows) == 2
    assert merged[0][2] - merged[0][0] == pytest.approx(8.0)


def test_perpendicular_walls_are_not_joined():
    walls = [(0, 0, 3, 0, T), (4, 0.2, 4, 3, T)]
    assert bridge_windows(walls, _glazing(3, 4, 0))[1] == []


def test_detect_finds_window_in_a_cut_wall(tmp_path):
    import ezdxf
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    wall = {"layer": "A-WALL"}
    # 8 x 6 m room, 200 mm double-line walls; the south wall has a window cut out
    # of both faces between x = 3000 and 4400 mm, with 3 glazing lines on layer "0".
    for (x1, y1, x2, y2) in [
        (0, 0, 3000, 0), (4400, 0, 8000, 0), (0, 200, 3000, 200), (4400, 200, 8000, 200),   # south faces
        (0, 6000, 8000, 6000), (0, 5800, 8000, 5800),                                       # north
        (0, 0, 0, 6000), (200, 200, 200, 5800),                                             # west
        (8000, 0, 8000, 6000), (7800, 200, 7800, 5800),                                     # east
        (3000, 0, 3000, 200), (4400, 0, 4400, 200),                                         # jambs
    ]:
        msp.add_line((x1, y1), (x2, y2), dxfattribs=wall)
    for y in (60, 100, 140):
        msp.add_line((3000, y), (4400, y), dxfattribs={"layer": "0"})
    # An interior partition and a room name: a bare empty rectangle is
    # indistinguishable from a sheet border, so a real plan always has these.
    for x in (5000, 5200):
        msp.add_line((x, 200), (x, 3000), dxfattribs=wall)
    msp.add_text("BEDROOM", height=250, dxfattribs={"layer": "TEXT"}).set_placement((1500, 3000))
    doc.saveas(str(tmp_path / "room.dxf"))
    result = detect_file(str(tmp_path / "room.dxf"), str(tmp_path / "cache"), cluster_id="c0")
    windows = [o for o in result["openings"] if o["type"] == "window"]
    assert len(windows) == 1 and windows[0]["width_m"] == pytest.approx(1.4, abs=0.05)
    south = [w for w in result["walls"] if w["y1"] == w["y2"] and w["y1"] > result["image_size"]["height"] / 2]
    assert len(south) == 1 and south[0]["length_ft"] == pytest.approx(8.0 / 0.3048, rel=0.03)   # one continuous wall
    assert windows[0]["wall_id"] == south[0]["id"]
