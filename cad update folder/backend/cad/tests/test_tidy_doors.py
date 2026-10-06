"""Door-swing cases (door gap, wall end, corner) and the wall clean-up rules."""
import math

import pytest

from cad.openings import attach_indices, find_openings
from cad.tidy import close_corners, drop_fixtures_and_blobs, drop_stubs, tidy_walls

T = 0.15


def _arc(cx, cy, r, a0_deg):
    """Quarter-circle swing: hinge at (cx, cy), ends at angle a0 and a0 + 90 (anticlockwise)."""
    a0, a1 = math.radians(a0_deg), math.radians(a0_deg + 90)
    return (cx, cy, r, 90.0, cx + r * math.cos(a0), cy + r * math.sin(a0), cx + r * math.cos(a1), cy + r * math.sin(a1))


def _doors(walls, arcs):
    out_walls, openings = find_openings(walls, arcs, [], [], [])
    return out_walls, attach_indices(out_walls, openings)


def test_door_in_a_gap_closed_end_on_the_far_piece():
    walls = [(0, 0, 3, 0, T), (3.9, 0, 8, 0, T)]               # 0.9 m door gap
    w, ops = _doors(walls, [_arc(3.0, 0, 0.9, 0)])             # hinge at the left jamb, closed end at the right
    assert len(ops) == 1 and ops[0]["type"] == "door" and ops[0]["width"] == pytest.approx(0.9)
    assert len(w) == 1                                          # the two pieces are one wall with a door in it


def test_door_at_a_wall_end_closing_onto_a_perpendicular_wall():
    walls = [(0, 0, 3, 0, T), (3.95, -2, 3.95, 3, T)]          # horizontal wall meets a vertical one, 0.95 m short
    _, ops = _doors(walls, [_arc(3.0, 0, 0.9, 0)])
    assert len(ops) == 1 and ops[0]["type"] == "door"


def test_door_at_the_end_of_a_wall_with_nothing_beyond():
    walls = [(0, 0, 3, 0, T)]                                  # wall just stops; the swing's far end lands in the open
    _, ops = _doors(walls, [_arc(3.0, 0, 0.9, 0)])
    assert len(ops) == 1 and ops[0]["type"] == "door" and ops[0]["wall_index"] == 0


def test_round_furniture_arc_away_from_walls_is_not_a_door():
    walls = [(0, 0, 8, 0, T)]
    _, ops = _doors(walls, [_arc(4.0, 3.0, 0.9, 0)])           # 3 m from any wall
    assert ops == []


# ── tidy ──────────────────────────────────────────────────────────────
def test_toilet_pan_box_is_dropped():
    box = [(0, 0, 0.5, 0, 0.08), (0.5, 0, 0.5, 0.5, 0.08), (0.5, 0.5, 0, 0.5, 0.08), (0, 0.5, 0, 0, 0.08)]
    walls = box + [(3, 0, 9, 0, T)]
    kept, n = drop_fixtures_and_blobs(walls, [])
    assert n == 4 and kept == [(3, 0, 9, 0, T)]


def test_stair_blob_is_dropped_but_a_thick_long_wall_stays():
    walls = [(0, 0, 1.2, 0, 0.61), (3, 0, 9, 0, 0.6)]
    kept, n = drop_fixtures_and_blobs(walls, [])
    assert n == 1 and kept == [(3, 0, 9, 0, 0.6)]


def test_door_jamb_stub_is_dropped_unless_it_carries_a_door():
    walls = [(0, 0, 6, 0, T), (3, 0, 3, 0.35, T)]              # 0.35 m nub hanging off the wall
    kept, n = drop_stubs(walls, [])
    assert n == 1 and len(kept) == 1
    kept, n = drop_stubs(walls, [{"x": 3.0, "y": 0.2, "type": "door", "width": 0.9}])
    assert n == 0 and len(kept) == 2


def test_open_corner_is_closed():
    walls = [(0, 0, 5, 0, T), (5.35, 0.1, 5.35, 4, T)]         # the horizontal wall stops 0.35 m short
    out, n = close_corners(walls, [])
    assert n == 1 and out[0][2] == pytest.approx(5.35, abs=1e-6)


def test_corner_beside_a_doorway_is_left_open():
    walls = [(0, 0, 5, 0, T), (5.35, 0.1, 5.35, 4, T)]
    out, n = close_corners(walls, [{"x": 5.15, "y": 0.0, "type": "door", "width": 0.9}])
    assert n == 0 and out[0][2] == 5


def test_tidy_keeps_ordinary_walls_untouched():
    walls = [(0, 0, 8, 0, T), (8, 0, 8, 6, T), (8, 6, 0, 6, T), (0, 6, 0, 0, T), (4, 0, 4, 6, T)]
    out, stats = tidy_walls(walls, [])
    assert len(out) == 5 and stats == {"fixture_walls_dropped": 0, "stubs_dropped": 0, "corners_closed": 0}
