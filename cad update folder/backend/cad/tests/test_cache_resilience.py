"""A damaged or locked cache must be rebuilt, never crash the upload (Nov 2026: "unable to
read the cad file" - one cached inspect.json had stray bytes at its end, and a cache folder
left by another Windows account locked its plan.dxf against this one)."""
import json
import os
import re
import sys
import types

import pytest

from cad import ai_assist, pipeline
from cad.converter import file_session_id
from cad.detect import detect_file
from cad.pipeline import inspect_file, session_dir, write_atomic

from .fixtures import write_simple_plan


def test_corrupt_inspect_cache_is_rebuilt(tmp_path):
    src = write_simple_plan(str(tmp_path / "plan.dxf"))
    cache = str(tmp_path / "cache")
    first = inspect_file(src, cache)
    path = os.path.join(session_dir(cache, first["session_id"]), "inspect.json")
    with open(path, "a", encoding="utf-8") as f:
        f.write("}{stray")                                    # what the broken cache looked like
    again = inspect_file(src, cache)
    assert again["cached"] is False and again["clusters"] == first["clusters"]
    with open(path, encoding="utf-8") as f:
        json.load(f)                                          # rewritten whole


def test_corrupt_state_is_rebuilt_by_detect(tmp_path):
    src = write_simple_plan(str(tmp_path / "plan.dxf"))
    cache = str(tmp_path / "cache")
    sid = inspect_file(src, cache)["session_id"]
    with open(os.path.join(session_dir(cache, sid), "state.pkl"), "wb") as f:
        f.write(b"not a pickle")
    assert detect_file(src, cache)["stats"]["rooms_detected"] >= 1


def test_unusable_cache_folder_is_skipped(tmp_path, monkeypatch):
    src = write_simple_plan(str(tmp_path / "plan.dxf"))
    cache = str(tmp_path / "cache")
    locked = session_dir(cache, file_session_id(src))
    os.makedirs(locked)
    real = pipeline._usable
    norm = lambda p: os.path.normcase(os.path.abspath(p))     # noqa: E731
    monkeypatch.setattr(pipeline, "_usable", lambda d: False if norm(d) == norm(locked) else real(d))
    result = inspect_file(src, cache)
    assert result["session_id"] != os.path.basename(locked)
    assert re.fullmatch(r"[0-9a-f]{16}", result["session_id"])   # still a valid id for the routes
    assert detect_file(src, cache)["session_id"] == result["session_id"]
    assert pipeline.read_progress(src, cache)["done"] is True


def test_usable_checks_every_file_and_writing(tmp_path, monkeypatch):
    d = tmp_path / "s"
    (d / "thumbs").mkdir(parents=True)
    (d / "plan.dxf").write_text("0\nEOF\n")
    (d / "thumbs" / "c0.png").write_bytes(b"\x89PNG")
    assert pipeline._usable(str(d)) is True
    real_open = open

    def deny(path, *a, **k):
        if str(path).endswith("plan.dxf"):
            raise PermissionError(13, "Permission denied", str(path))
        return real_open(path, *a, **k)

    monkeypatch.setattr("builtins.open", deny)
    assert pipeline._usable(str(d)) is False


def test_write_atomic_never_leaves_a_half_file(tmp_path):
    path = str(tmp_path / "inspect.json")
    write_atomic(path, '{"a": 1}')
    with pytest.raises(TypeError):
        write_atomic(path, 12345)                             # fails mid-write
    with open(path, encoding="utf-8") as f:
        assert json.load(f) == {"a": 1}                       # old content intact
    assert os.listdir(tmp_path) == ["inspect.json"]           # no temp file left


def test_corrupt_ai_cache_runs_the_model_again(tmp_path, monkeypatch):
    cache_json = str(tmp_path / "ai.json")
    with open(cache_json, "w", encoding="utf-8") as f:
        f.write('{"openings": [')
    fake = types.ModuleType("ml_detector")
    fake.detect_floor_plan_ml = lambda path: {"walls": [], "rooms": [], "openings": []}
    monkeypatch.setitem(sys.modules, "ml_detector", fake)
    assert ai_assist.image_ai(str(tmp_path / "render.png"), cache_json)["openings"] == []
