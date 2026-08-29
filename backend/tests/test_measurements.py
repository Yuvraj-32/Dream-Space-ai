"""Scale-calibration tests.

A wrong scale is worse than no scale: the 3D stage sizes the entire world from
`scale_ft_per_px`, so a bad value silently turns a flat into a cathedral while
the walkthrough still appears to work. These tests pin the guard that makes
_calibrate return None rather than guess.
"""
import pytest

from measurements import _calibrate, estimate_scale_from_doors


def _result(doors_px, building_px=1500):
    """Detection-shaped dict with `doors_px` door widths and a square building."""
    return {
        "walls": [
            {"x1": 0, "y1": 0, "x2": building_px, "y2": 0},
            {"x1": 0, "y1": building_px, "x2": building_px, "y2": building_px},
        ],
        "rooms": [],
        "openings": [
            {"id": f"o{i}", "type": "door", "x": 0, "y": 0, "width_px": w}
            for i, w in enumerate(doors_px)
        ],
    }


def _tok(text, values, center, is_pair):
    return {"text": text, "values_ft": values, "center": center,
            "conf": 0.9, "is_pair": is_pair}


def _room(x, y, w, h):
    return {"bbox": {"x": x, "y": y, "w": w, "h": h}}


def test_agreeing_room_labels_calibrate():
    """Two room labels that agree → a scale close to the true one."""
    # 10ft over 100px and 20ft over 200px both mean 0.1 ft/px.
    rooms = [_room(0, 0, 100, 100), _room(200, 0, 200, 200)]
    tokens = [
        _tok("10' x 10'", [10.0, 10.0], (50, 50), True),
        _tok("20' x 20'", [20.0, 20.0], (300, 100), True),
    ]
    assert _calibrate(tokens, rooms, (0, 0, 400, 200)) == pytest.approx(0.1)


def test_disagreeing_samples_reject():
    """Samples that disagree by more than the allowed spread → no scale."""
    rooms = [_room(0, 0, 100, 100), _room(200, 0, 200, 200)]
    tokens = [
        _tok("10' x 10'", [10.0, 10.0], (50, 50), True),     # 0.10 ft/px
        _tok("80' x 80'", [80.0, 80.0], (300, 100), True),   # 0.40 ft/px
    ]
    assert _calibrate(tokens, rooms, (0, 0, 400, 200)) is None


def test_single_overall_label_alone_does_not_calibrate():
    """The regression this guard was added for.

    Garbled OCR on a textured plan yielded only two non-pair tokens
    ("ICv X 106'", "49 *43'"). The old fallback divided those by the building
    width and reported the unit as 74.5 x 68 ft with a 1459 sq ft kitchen.
    With no room-label corroboration there must be no scale at all.
    """
    tokens = [
        _tok("ICv X 106'", [106.0], (700, 100), False),
        _tok("49 *43'", [43.0], (900, 120), False),
    ]
    assert _calibrate(tokens, rooms=[], building_bbox=(0, 0, 1200, 1200)) is None


def test_no_tokens_gives_no_scale():
    assert _calibrate([], [], (0, 0, 100, 100)) is None


# ── Door-width fallback ───────────────────────────────────────────────

def test_door_width_recovers_known_scale():
    """The 3br CAD plan, whose printed dimensions give 0.02633 ft/px.

    Its 8 detected doors have a median width of 96 px. Door calibration must
    land close to the measured scale — this is what makes the 3D world
    life-sized on plans whose dimension text does not OCR.
    """
    got = estimate_scale_from_doors(_result([96.0] * 8, building_px=1519))
    assert got == pytest.approx(0.02633, rel=0.10)


def test_door_width_needs_more_than_one_door():
    assert estimate_scale_from_doors(_result([96.0])) is None
    assert estimate_scale_from_doors(_result([])) is None


def test_disagreeing_doors_reject():
    """Widths that don't cluster are mis-detections, not doors."""
    assert estimate_scale_from_doors(_result([20.0, 95.0, 300.0, 8.0])) is None


def test_implausible_building_rejected():
    """A door width implying a 300 m building means the doors were wrong."""
    # 2 px doors over a 1500 px building → ~600 m across.
    assert estimate_scale_from_doors(_result([2.0, 2.0, 2.0])) is None


def test_scale_is_resolution_independent():
    """The same plan scanned at 2x must yield the same real-world size.

    This is the property the old 1px=1cm fallback lacked: it made one house
    15.2 m wide from a large scan and 2.9 m wide from a small one.
    """
    small = estimate_scale_from_doors(_result([48.0] * 4, building_px=750))
    large = estimate_scale_from_doors(_result([96.0] * 4, building_px=1500))
    assert small is not None and large is not None
    assert small * 750 == pytest.approx(large * 1500, rel=1e-6)
