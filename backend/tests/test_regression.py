"""
Regression harness for the floor-plan detector.

Two layers:
  1. Range assertions — output must fall inside hand-counted ground-truth
     ranges (tests/ground_truth.py). Catches gross regressions.
  2. Snapshot — the pipeline "fingerprint" (per-stage stat counts + final
     totals) is written to tests/snapshots/<fixture>.json. A change that
     stays inside the range still shows up as a snapshot diff, so every
     pipeline tweak is visible and reviewable.

Update snapshots intentionally with:  UPDATE_SNAPSHOTS=1 pytest
"""
import json
import os

import pytest

from conftest import fixture_path
from ground_truth import GROUND_TRUTH

SNAPSHOT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshots")
UPDATE = os.environ.get("UPDATE_SNAPSHOTS") == "1"

FIXTURES = sorted(GROUND_TRUTH.keys())


def _fingerprint(result: dict) -> dict:
    """Stable, diff-friendly summary of a detection result.

    Excludes raw coordinates (noisy, change on any threshold tweak) and
    keeps the counts that describe pipeline behavior."""
    s = result["stats"]
    return {
        "image_size": result["image_size"],
        "counts": {
            "walls": len(result["walls"]),
            "rooms": len(result["rooms"]),
            "openings": len(result["openings"]),
            "doors": sum(1 for o in result["openings"] if o["type"] == "door"),
            "windows": sum(1 for o in result["openings"] if o["type"] == "window"),
            "main_walls": sum(1 for w in result["walls"] if w["wall_type"] == "main_wall"),
            "partition_walls": sum(1 for w in result["walls"] if w["wall_type"] == "partition"),
        },
        "pipeline_stages": {
            k: s.get(k)
            for k in (
                "raw_lines", "after_merge_p1", "after_merge_p2",
                "after_length_filter", "after_thickness", "after_endpoint_snap",
                "after_coaxial_merge", "after_isolated_removal",
                "diagonal_removed", "phantom_removed", "walls_final",
                "door_arcs_found",
            )
        },
    }


@pytest.fixture(scope="session")
def results(detect):
    """Run detection once per fixture for the whole session."""
    return {name: detect(fixture_path(name)) for name in FIXTURES}


@pytest.mark.parametrize("fixture", FIXTURES)
def test_within_ground_truth_ranges(results, fixture):
    result = results[fixture]
    gt = GROUND_TRUTH[fixture]
    fp = _fingerprint(result)["counts"]

    checks = {
        "rooms": fp["rooms"],
        "walls": fp["walls"],
        "openings": fp["openings"],
        "doors": fp["doors"],
        "windows": fp["windows"],
    }
    failures = []
    for metric, value in checks.items():
        lo, hi = gt[metric]
        if not (lo <= value <= hi):
            failures.append(f"{metric}={value} outside expected [{lo}, {hi}]")
    assert not failures, f"{fixture}: " + "; ".join(failures)


@pytest.mark.parametrize("fixture", FIXTURES)
def test_snapshot(results, fixture):
    fp = _fingerprint(results[fixture])
    snap_path = os.path.join(SNAPSHOT_DIR, fixture + ".json")

    if UPDATE or not os.path.exists(snap_path):
        os.makedirs(SNAPSHOT_DIR, exist_ok=True)
        with open(snap_path, "w") as f:
            json.dump(fp, f, indent=2)
        if not UPDATE:
            pytest.skip(f"created new snapshot {fixture}.json")
        return

    with open(snap_path) as f:
        stored = json.load(f)
    assert fp == stored, (
        f"{fixture}: fingerprint changed vs snapshot.\n"
        f"stored={json.dumps(stored, indent=2)}\n"
        f"current={json.dumps(fp, indent=2)}\n"
        f"If intentional, re-run with UPDATE_SNAPSHOTS=1"
    )
