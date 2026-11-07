"""Two NITIN BHAI first-floor failures: a rug's zig-zag on the wall layer must not
decide the wall thickness (only lines on the drawing's grid do), and an open door
leaf resting against a wall face is not the doorway."""
import math

import pytest

from cad.openings import _door_from_arc, _overlap
from cad.walls import _Line, _on_main_axes


def _kept(segs):
    lines = [_Line(*s) for s in segs]
    marker = [[(0.1, 0.0, 1.0, k)] for k in range(len(lines))]       # one dummy candidate per line
    return [bool(c) for c in _on_main_axes(lines, marker)]


def test_wall_thickness_is_learnt_from_the_drawing_grid_only():
    # x/y walls (36 m) plus a heavier diagonal pattern (a rug, a hatch: 42 m), so the
    # drawing's dominant direction is the rug's: still only the walls count.
    walls = [(0, 0, 10, 0), (0, 0.127, 10, 0.127), (0, 0, 0, 8), (0.127, 0, 0.127, 8)]
    rug = [(1 + 0.1 * k, 1, 4 + 0.1 * k, 4) for k in range(10)]
    assert _kept(walls + rug) == [True] * 4 + [False] * 10


def test_a_plan_drawn_rotated_uses_its_own_grid():
    c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
    rot = [(0, 0, 10 * c, 10 * s), (0, 0, -8 * s, 8 * c), (1, 1, 1 + 9 * c, 1 + 9 * s)]
    clutter = [(0, 0, 0.4, 0.3)]                                      # short, off-grid
    assert _kept(rot + clutter) == [True, True, True, False]


def test_no_clear_grid_keeps_every_candidate():
    fan = [(0, 0, math.cos(math.radians(a)) * 5, math.sin(math.radians(a)) * 5) for a in range(0, 180, 12)]
    assert all(_kept(fan))


def test_open_leaf_against_a_wall_face_is_not_the_doorway():
    # A partition (y = 4.0) and a wall coming down to a doorway (x = 5.0, ends at 4.9).
    # The door hinges just above the partition's face; its open leaf lies along that
    # face, 5-7 cm outside the wall band. The doorway is the gap in the x = 5.0 wall.
    walls = [(5.0, 8.0, 5.0, 4.9, 0.127), (0.0, 4.0, 10.0, 4.0, 0.127)]
    arc = (5.0, 4.13, 0.8, 90.0, 4.2, 4.13, 5.0, 4.93)
    door = _door_from_arc(arc, walls)
    assert (door["x"], door["y"]) == (pytest.approx(5.0), pytest.approx(4.53))


def test_a_window_on_another_wall_is_not_merged_into_a_door():
    # THREE BEDROOM: a 1.4 m double door, and a window on the parallel wall 1.3 m away.
    door = {"type": "door", "x": 5.0, "y": 5.0, "width": 1.4, "chord": (4.3, 5.0, 5.7, 5.0)}
    window_elsewhere = {"type": "window", "x": 5.05, "y": 3.7, "width": 1.2}
    window_in_line = {"type": "window", "x": 5.4, "y": 5.05, "width": 1.2}
    assert not _overlap(door, window_elsewhere) and not _overlap(window_elsewhere, door)
    assert _overlap(door, window_in_line)
