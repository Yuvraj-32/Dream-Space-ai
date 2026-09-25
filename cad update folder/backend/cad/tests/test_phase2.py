"""Phase 2 tests: walls from CAD faces, openings, rooms, /cad/detect.

Run from backend/:  venv/Scripts/python.exe -m pytest "../cad update folder/backend/cad/tests"
"""
import math

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cad.detect import detect_file
from cad.rooms import parse_label_dims_ft
from cad.routes import create_cad_router
from cad.walls import build_walls, pair_faces

from .fixtures import write_simple_plan

NAME = "0123456789abcdef0123456789abcdef.dxf"


def _len(w):
    return math.hypot(w[2] - w[0], w[3] - w[1])


# ── walls ─────────────────────────────────────────────────────────────
def test_faces_drawn_in_opposite_directions_pair():
    # A closed wall outline runs its two faces in opposite directions.
    pieces, _, _, modes = pair_faces([(0, 0, 5, 0), (5, 0.2, 0, 0.2)])
    assert pieces and modes == [0.2]
    walls, _ = build_walls([(0, 0, 5, 0), (5, 0.2, 0, 0.2)], [])
    assert len(walls) == 1
    w = walls[0]
    assert abs(w[4] - 0.2) < 1e-6 and abs(_len(w) - 5.0) < 1e-6
    assert abs(w[1] - 0.1) < 1e-6 and abs(w[3] - 0.1) < 1e-6


def test_nearest_partner_ignores_plaster_line():
    # Faces at 0 and 0.2 plus an extra line at 0.5: one 0.2 m wall, not a 0.5 m one.
    walls, _ = build_walls([(0, 0, 6, 0), (0, 0.2, 6, 0.2), (0, 0.5, 6, 0.5)] * 1, [])
    assert all(abs(w[4] - 0.2) < 0.03 for w in walls)


def test_t_junction_keeps_main_wall_continuous():
    t = 0.2
    segs = [
        (0, 0, 10, 0),                                      # outer face, continuous
        (0, t, 4.9, t), (5.1, t, 10, t),                    # inner face, broken by partition
        (4.9, t, 4.9, 5), (5.1, t, 5.1, 5),                 # partition faces
    ]
    walls, _ = build_walls(segs, [])
    horizontal = [w for w in walls if abs(w[1] - w[3]) < 1e-6]
    vertical = [w for w in walls if abs(w[0] - w[2]) < 1e-6]
    assert len(horizontal) == 1 and _len(horizontal[0]) == pytest.approx(10.0, abs=1e-6)
    assert len(vertical) == 1
    assert min(vertical[0][1], vertical[0][3]) == pytest.approx(t / 2, abs=1e-6)  # reaches main centerline


def test_l_corner_is_closed():
    t = 0.2
    segs = [(0, 0, 6, 0), (t, t, 6, t),          # horizontal wall faces
            (0, 0, 0, 6), (t, t, t, 6)]          # vertical wall faces
    walls, _ = build_walls(segs, [])
    ends = [(round(x, 6), round(y, 6)) for w in walls for x, y in ((w[0], w[1]), (w[2], w[3]))]
    assert (t / 2, t / 2) in ends and ends.count((t / 2, t / 2)) == 2


def test_stairs_are_not_walls():
    treads = [(0, 0.28 * k, 1.0, 0.28 * k) for k in range(12)]
    walls, _ = build_walls(treads + [(3, 0, 9, 0), (3, 0.2, 9, 0.2)], [])
    assert len(walls) == 1 and _len(walls[0]) == pytest.approx(6.0)


@pytest.mark.parametrize("text,expected", [
    ("BED ROOM - 3 12'-3\"X14'-0\"", [12.25, 14.0]),
    ("KITCHEN 3600 X 3000", [11.81, 9.84]),
    ("BATH 2.4 x 1.8", [7.87, 5.91]),
    ("LIVING ROOM", None),
])
def test_label_dimensions(text, expected):
    assert parse_label_dims_ft(text) == expected


# ── full detection on the synthetic plan ─────────────────────────────
def _check_plan(result):
    rooms = {r["type"]: r for r in result["rooms"]}
    assert set(rooms) == {"bedroom", "kitchen"}
    # Net interior of each half: (10 - 0.2 - 0.2 wall) / 2 ... = 4.7 m x 7.6 m
    for r in rooms.values():
        assert r["area_sqft"] == pytest.approx(4.7 * 7.6 * 10.7639, rel=0.03)
        assert sorted(r["computed_dim_ft"]) == pytest.approx(sorted([4.7 / 0.3048, 7.6 / 0.3048]), rel=0.03)
    doors = [o for o in result["openings"] if o["type"] == "door"]
    assert len(doors) == 1 and doors[0]["width_m"] == pytest.approx(0.9, abs=0.02)
    walls = {w["id"]: w for w in result["walls"]}
    assert doors[0]["wall_id"] in walls
    assert all(w["thickness_m"] == pytest.approx(0.2, abs=0.02) for w in result["walls"])
    assert result["stats"]["engine"] == "cad_vector"
    assert result["stats"]["scale_ft_per_px"] > 0
    for key in ("image_size", "walls", "rooms", "openings", "stats", "measurements"):
        assert key in result


def test_detect_simple_plan(tmp_path):
    result = detect_file(write_simple_plan(str(tmp_path / "plan.dxf")), str(tmp_path / "cache"))
    _check_plan(result)


def test_detect_corrects_mislabelled_units(tmp_path):
    # Drawn in metres, labelled millimetres: same house, same result.
    result = detect_file(write_simple_plan(str(tmp_path / "m.dxf"), units=4, s=0.001), str(tmp_path / "cache"))
    _check_plan(result)


def test_detect_door_block_lines_are_not_walls(tmp_path):
    result = detect_file(write_simple_plan(str(tmp_path / "plan.dxf")), str(tmp_path / "cache"))
    # The door leaf (a 0.9 m line inside the block) must not become a wall.
    assert not any(w["length_ft"] == pytest.approx(0.9 / 0.3048, abs=0.1) for w in result["walls"])


# ── routes ────────────────────────────────────────────────────────────
@pytest.fixture
def client(tmp_path):
    upload = tmp_path / "uploads"
    upload.mkdir()
    write_simple_plan(str(upload / NAME))
    app = FastAPI()
    app.include_router(create_cad_router(str(upload), str(upload / "cad_cache")))
    return TestClient(app)


def test_route_detect_and_preview(client):
    res = client.post(f"/cad/detect/{NAME}")
    assert res.status_code == 200, res.text
    body = res.json()
    _check_plan(body)
    img = client.get(body["preview_url"])
    assert img.status_code == 200 and img.headers["content-type"] == "image/png"


def test_route_detect_role_override(client):
    res = client.post(f"/cad/detect/{NAME}", json={"layer_roles": {"A-WALL": "ignore"}})
    assert res.status_code == 200 and res.json()["walls"] == []


@pytest.mark.parametrize("payload,status", [
    ({"layer_roles": {"A-WALL": "roof"}}, 422),
    ({"cluster_id": "c9"}, 422),
    ({"cluster_id": "../x"}, 400),
    ({"units": "furlong"}, 422),
])
def test_route_detect_rejects_bad_input(client, payload, status):
    assert client.post(f"/cad/detect/{NAME}", json=payload).status_code == status


def test_route_preview_rejects_bad_paths(client):
    assert client.get("/cad/preview/0123456789abcdef/../../secret.png").status_code in (400, 404)
    assert client.get("/cad/preview/0123456789abcdef/plan.dxf").status_code == 400
