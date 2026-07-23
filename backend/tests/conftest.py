"""Shared pytest fixtures for detector regression tests."""
import os
import sys

import pytest

# Make the backend package importable (detector.py lives one level up).
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_DIR)

FIXTURES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def fixture_path(name: str) -> str:
    return os.path.join(FIXTURES_DIR, name)


@pytest.fixture(scope="session")
def detect():
    """Return the detect_floor_plan function (imported lazily so a missing
    OpenCV install produces a clear collection error, not an import crash)."""
    from detector import detect_floor_plan
    return detect_floor_plan
