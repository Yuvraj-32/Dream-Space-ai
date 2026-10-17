"""Phase 1 unit tests: units, layer roles, clustering, inspect pipeline and routes.

Run from backend/:  venv/Scripts/python.exe -m pytest "../cad update folder/backend/cad/tests"
"""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cad.converter import ConversionFailed
from cad.loader import flatten, header_units, load_doc
from cad.pipeline import inspect_file
from cad.routes import create_cad_router
from cad.units import resolve_units
from cad.vocab import room_type_for

from .fixtures import write_empty, write_labels_only, write_sheet, write_simple_plan


def _layers(result):
    return {l["name"]: l for l in result["layers"]}


# ── units ─────────────────────────────────────────────────────────────
def _units_for(path):
    doc, _ = load_doc(path)
    _, header_name, header_mpu = header_units(doc)
    records, _, _ = flatten(doc, header_mpu or 0.001)
    return resolve_units(records, header_name)


def test_units_header_confirmed(tmp_path):
    u = _units_for(write_simple_plan(str(tmp_path / "mm.dxf"), units=4))
    assert (u["name"], u["confidence"]) == ("mm", "header")


def test_units_wrong_header_corrected(tmp_path):
    # Drawn in metres but labelled millimetres — the gazebo sample's situation.
    u = _units_for(write_simple_plan(str(tmp_path / "m_as_mm.dxf"), units=4, s=0.001))
    assert (u["name"], u["confidence"], u["header"]) == ("m", "corrected", "mm")


def test_units_unitless_guessed(tmp_path):
    u = _units_for(write_simple_plan(str(tmp_path / "unitless.dxf"), units=0))
    assert (u["name"], u["confidence"]) == ("mm", "guess")


# ── layers ────────────────────────────────────────────────────────────
def test_layer_roles(tmp_path):
    r = inspect_file(write_simple_plan(str(tmp_path / "plan.dxf")), str(tmp_path / "cache"))
    layers = _layers(r)
    assert layers["A-WALL"]["suggested_role"] == "wall"
    assert layers["A-WALL"]["confidence"] >= 0.9
    assert layers["DOOR"]["suggested_role"] == "door"
    assert layers["TEXT"]["suggested_role"] == "room_label"
    assert layers["FURNITURE"]["suggested_role"] == "ignore"


def test_block_content_inherits_insert_layer(tmp_path):
    r = inspect_file(write_simple_plan(str(tmp_path / "plan.dxf")), str(tmp_path / "cache"))
    layers = _layers(r)
    # The door block's arc is drawn on layer "0" inside the block.
    assert layers["DOOR"]["door_arcs"] == 1
    assert "0" not in layers


# ── clusters ──────────────────────────────────────────────────────────
def test_sheet_clusters(tmp_path):
    r = inspect_file(write_sheet(str(tmp_path / "sheet.dxf")), str(tmp_path / "cache"))
    clusters = r["clusters"]
    plans = [c for c in clusters if c["kind_guess"] == "floor_plan"]
    assert len(plans) == 2, [(c["id"], c["kind_guess"], c["size_m"]) for c in clusters]
    for c in plans:
        assert c["size_m"] == [10.0, 8.0]
    assert r["stats"]["frames_removed"] == 1
    assert r["stats"]["tiny_groups_dropped"] >= 1           # the far-away point
    assert clusters[0]["suggested"] and clusters[0]["kind_guess"] == "floor_plan"
    assert sum(c["suggested"] for c in clusters) == 1
    elevation = [c for c in clusters if c["diag_frac"] > 0.2]
    assert elevation and elevation[0]["kind_guess"] != "floor_plan"


def test_labels_without_walls_are_flagged_not_suggested(tmp_path):
    r = inspect_file(write_labels_only(str(tmp_path / "labels.dxf")), str(tmp_path / "cache"))
    wallless = [c for c in r["clusters"] if c["walls_missing"]]
    assert len(wallless) == 1
    assert wallless[0]["kind_guess"] == "plan_without_walls"
    assert not wallless[0]["suggested"]
    assert any("no walls" in w for w in r["warnings"])


def test_empty_drawing_is_a_conversion_failure(tmp_path):
    with pytest.raises(ConversionFailed):
        inspect_file(write_empty(str(tmp_path / "empty.dxf")), str(tmp_path / "cache"))


def test_inspect_is_cached(tmp_path):
    path = write_simple_plan(str(tmp_path / "plan.dxf"))
    first = inspect_file(path, str(tmp_path / "cache"))
    second = inspect_file(path, str(tmp_path / "cache"))
    assert first["cached"] is False and second["cached"] is True
    assert first["session_id"] == second["session_id"]


# ── vocabulary ────────────────────────────────────────────────────────
@pytest.mark.parametrize("label,expected", [
    ("BED ROOM - 3 12'-3\"X14'-0\"", "bedroom"),
    ("MASTER B/ROOM", "bedroom"),
    ("LIVING ROOM 17'-9\"X15'-0\"", "living_room"),
    ("SALA FAMILIAR", "living_room"),
    ("TOILET 4'-6\"X4'-6\"", "bath"),
    ("WC", "bath"),
    ("POOJA", "pooja"),
    ("SCALE 1:100", None),
    ("W2", None),
])
def test_room_vocabulary(label, expected):
    assert room_type_for(label) == expected


# ── routes ────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path):
    upload = tmp_path / "uploads"
    upload.mkdir()
    app = FastAPI()
    app.include_router(create_cad_router(str(upload), str(upload / "cad_cache")))
    return TestClient(app), upload


def test_route_inspect_and_thumbnail(client):
    c, upload = client
    name = "0123456789abcdef0123456789abcdef.dxf"
    write_simple_plan(str(upload / name))
    res = c.post(f"/cad/inspect/{name}")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["clusters"] and body["units"]["name"] == "mm"
    thumb = c.get(body["clusters"][0]["thumbnail_url"])
    assert thumb.status_code == 200 and thumb.headers["content-type"] == "image/png"


@pytest.mark.parametrize("name,status", [
    ("../main.py", 404),                          # path traversal never reaches the handler
    ("not-a-hash.dxf", 400),
    ("0123456789abcdef0123456789abcdef.png", 400),
    ("0123456789abcdef0123456789abcdef.dxf", 404),
])
def test_route_inspect_rejects_bad_names(client, name, status):
    c, _ = client
    assert c.post(f"/cad/inspect/{name}").status_code == status


def test_route_thumbnail_rejects_bad_paths(client):
    c, _ = client
    assert c.get("/cad/thumb/xyz/c0.png").status_code == 400
    assert c.get("/cad/thumb/0123456789abcdef/../x.png").status_code in (400, 404)


def test_route_health(client):
    c, _ = client
    body = c.get("/cad/health").json()
    assert set(body) == {"dwg2dxf", "path", "version"}


# ── main.py hook-in: images unchanged, CAD accepted ───────────────────
@pytest.fixture
def main_client(tmp_path, monkeypatch):
    import importlib
    import sys
    monkeypatch.chdir(tmp_path)          # main.py creates "uploads/" relative to cwd
    sys.modules.pop("main", None)
    main = importlib.import_module("main")
    yield TestClient(main.app)
    sys.modules.pop("main", None)


def test_upload_accepts_cad_and_keeps_images(main_client, tmp_path):
    dxf = write_simple_plan(str(tmp_path / "plan.dxf"))
    with open(dxf, "rb") as f:
        res = main_client.post("/upload", files={"file": ("My Plan.dxf", f, "application/dxf")})
    assert res.status_code == 200 and res.json()["kind"] == "cad"
    cad_name = res.json()["filename"]

    res = main_client.post("/upload", files={"file": ("photo.png", b"\x89PNG fake", "image/png")})
    assert res.status_code == 200 and res.json()["kind"] == "image"

    res = main_client.post("/upload", files={"file": ("notes.txt", b"hi", "text/plain")})
    assert res.status_code == 400

    res = main_client.post(f"/detect/{cad_name}")
    assert res.status_code == 200 and res.json()["walls"] and res.json()["preview_url"]
    assert main_client.post(f"/cad/inspect/{cad_name}").status_code == 200
