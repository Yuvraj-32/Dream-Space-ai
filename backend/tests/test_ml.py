"""
ML-engine (CubiCasa5k) tests. Separate from the fast classical suite because
the model load + CPU inference is slow (~10-15s). Skipped automatically if
torch or the weights are unavailable, so the default suite stays green on a
clean checkout without the ML setup.

Run just these with:  pytest tests/test_ml.py
"""
import pytest

from conftest import fixture_path

# Skip the whole module if the ML stack isn't installed.
ml = pytest.importorskip("torch", reason="torch not installed")

try:
    from ml_detector import detect_floor_plan_ml, _WEIGHTS
    import os
    _HAVE_WEIGHTS = os.path.exists(_WEIGHTS)
except Exception:
    _HAVE_WEIGHTS = False

pytestmark = pytest.mark.skipif(
    not _HAVE_WEIGHTS, reason="CubiCasa weights not downloaded"
)

# Loose sanity ranges — the ML model should comfortably clear the classical
# floor. These assert "the engine produces a sensible structured result",
# not exact counts.
ML_EXPECT = {
    "3br_cad.jpg":       {"walls": (8, 60), "rooms": (4, 12), "openings": (6, 30)},
    "truoba_render.jpg": {"walls": (4, 40), "rooms": (1, 8),  "openings": (2, 20)},
}


@pytest.fixture(scope="session")
def ml_results():
    return {name: detect_floor_plan_ml(fixture_path(name)) for name in ML_EXPECT}


@pytest.mark.parametrize("fixture", sorted(ML_EXPECT))
def test_ml_schema(ml_results, fixture):
    """Output must match the classical JSON schema so the frontend is engine-agnostic."""
    r = ml_results[fixture]
    assert set(r.keys()) >= {"image_size", "walls", "rooms", "openings", "stats"}
    assert r["stats"]["engine"] == "ml_cubicasa"
    for wall in r["walls"]:
        assert {"id", "x1", "y1", "x2", "y2", "wall_type", "thickness"} <= set(wall)
    for room in r["rooms"]:
        assert {"id", "area", "bbox", "centroid", "polygon", "type"} <= set(room)
    for op in r["openings"]:
        assert op["type"] in ("door", "window")
        assert {"id", "wall_id", "x", "y", "width_px"} <= set(op)


@pytest.mark.parametrize("fixture", sorted(ML_EXPECT))
def test_ml_sane_counts(ml_results, fixture):
    r = ml_results[fixture]
    exp = ML_EXPECT[fixture]
    counts = {
        "walls": len(r["walls"]),
        "rooms": len(r["rooms"]),
        "openings": len(r["openings"]),
    }
    failures = [
        f"{k}={v} outside {exp[k]}"
        for k, v in counts.items()
        if not (exp[k][0] <= v <= exp[k][1])
    ]
    assert not failures, f"{fixture}: " + "; ".join(failures)
