"""The image-AI assist: door referee, chord merging, last-resort fallback, and that CAD
detection carries on when the image model can't run."""
import ezdxf
import pytest

from cad import ai_assist
from cad.detect import detect_file

WALL_T = 230  # mm


def _door(x, y, w=0.8):
    return {"type": "door", "x": x, "y": y, "width": w, "chord": None}


# A swing hinged at (3.5, 12.45), r 0.75: candidate doorways are along the vertical
# wall (centre (3.5, 12.075)) or along the horizontal wall (centre (3.875, 12.45)).
ARC = (3.5, 12.45, 0.75, 90.0, 3.5, 11.7, 4.25, 12.45)


def test_referee_takes_the_doorway_the_model_clearly_sees():
    openings = [_door(3.5, 12.075)]                       # rules: vertical wall
    out, moved = ai_assist.referee_doors(openings, [ARC], ai_doors=[(3.89, 12.49)])
    assert moved == 1
    (d,) = out
    assert (round(d["x"], 3), round(d["y"], 3)) == (3.875, 12.45)
    assert d["source"] == "ai_referee"


def test_referee_keeps_the_rules_when_the_model_is_unsure_or_silent():
    openings = [_door(3.5, 12.075)]
    for ai in ([], [(3.7, 12.25)], [(9.0, 9.0)]):          # nothing / halfway between / far away
        out, moved = ai_assist.referee_doors(openings, [ARC], ai)
        assert moved == 0 and out == openings


def test_referee_splits_two_doors_the_rules_merged():
    # NITIN ground floor: two bedroom doors either side of a partition, merged by the
    # rules into one wide door on the partition; the model sees both doorways.
    left = (3.28, 7.42, 0.75, 92.0, 3.31, 8.17, 2.53, 7.42)
    right = (3.55, 7.42, 0.75, 92.0, 3.52, 8.17, 4.30, 7.42)
    openings = [_door(3.42, 7.79, 1.5), _door(1.06, 6.24, 0.66)]
    out, moved = ai_assist.referee_doors(openings, [left, right], ai_doors=[(2.91, 7.59), (3.91, 7.59)])
    doors = sorted((o["x"], o["y"]) for o in out)
    assert moved == 1
    assert doors == [pytest.approx((1.06, 6.24)), pytest.approx((2.905, 7.42)), pytest.approx((3.925, 7.42))]


def test_merge_chords_joins_double_door_leaves_only():
    leaves = [(0.0, 0.0, 0.6, 0.0), (1.2, 0.0, 0.6, 0.0)]             # two leaves meeting mid-opening
    apart = [(0.0, 0.0, 0.8, 0.0), (1.1, 0.0, 1.9, 0.0)]              # two doors 0.3 m apart
    assert len(ai_assist.merge_chords(leaves)) == 1
    assert len(ai_assist.merge_chords(apart)) == 2


def _plan(path):
    """Two rooms with a door each, real swing arcs, labels."""
    doc = ezdxf.new("R2010", units=4)
    msp = doc.modelspace()
    for (x0, y0, x1, y1) in ((0, 0, 10000, 8000), (WALL_T, WALL_T, 10000 - WALL_T, 8000 - WALL_T)):
        msp.add_lwpolyline([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], close=True, dxfattribs={"layer": "A-WALL"})
    for x in (5000 - WALL_T / 2, 5000 + WALL_T / 2):
        msp.add_line((x, WALL_T), (x, 3000), dxfattribs={"layer": "A-WALL"})
        msp.add_line((x, 3900), (x, 8000 - WALL_T), dxfattribs={"layer": "A-WALL"})
    msp.add_arc((5000, 3000), 900, 90, 180, dxfattribs={"layer": "DOOR"})
    msp.add_line((5000, 3000), (5000, 3900), dxfattribs={"layer": "DOOR"})
    for text, x in (("BEDROOM", 2000), ("KITCHEN", 7000)):
        msp.add_text(text, height=250, dxfattribs={"layer": "TEXT"}).set_placement((x, 4000))
    doc.saveas(path)
    return path


def test_detection_carries_on_when_the_model_cannot_run(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAMSPACE_CAD_AI", "1")
    monkeypatch.setattr(ai_assist, "image_ai", lambda render, cache: None)
    det = detect_file(_plan(str(tmp_path / "p.dxf")), str(tmp_path / "cache"))
    assert det["stats"]["ai_assist"] == {"used": False, "reason": "image model not available"}
    assert det["stats"]["rooms_detected"] == 2


def test_fallback_only_when_the_rules_find_no_rooms(tmp_path, monkeypatch):
    monkeypatch.setenv("DREAMSPACE_CAD_AI", "1")
    fake = {"image_size": {"width": 10, "height": 10}, "walls": [], "openings": [], "door_arcs": [],
            "rooms": [{"id": "room_0"}, {"id": "room_1"}, {"id": "room_2"}]}
    monkeypatch.setattr(ai_assist, "image_ai", lambda render, cache: fake)
    path = _plan(str(tmp_path / "p.dxf"))
    det = detect_file(path, str(tmp_path / "cache"))
    assert "fallback" not in det["stats"]["ai_assist"] and det["stats"]["rooms_detected"] == 2
    # Mark the wall layer as ignore: the rules now find no rooms, so the model's result stands in.
    det = detect_file(path, str(tmp_path / "cache"), layer_roles={"A-WALL": "ignore"})
    assert det["stats"]["ai_assist"]["fallback"] is True
    assert det["rooms"] == fake["rooms"]
