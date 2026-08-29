"""
measurements.py — turn pixel detections into real-world measurements.

Reads the dimension labels printed on a floor plan (EasyOCR), calibrates a
pixels-per-foot scale, and annotates a detection result with:
  - each wall's length in feet
  - each room's labeled dimension (what the plan says) and computed dimension
    (from geometry × scale)
  - the overall building size

Scale calibration is robust: every room-dimension label ("9'-0\" x 12'-0\"")
is matched to its detected room's pixel bounding box, giving many
feet↔pixel samples; the median ratio is the scale. This tolerates a few bad
OCR reads or room mismatches.

EasyOCR is free and CPU-only. The reader is a module singleton (slow to load).
"""
import re
from typing import Any, Optional

import numpy as np

_reader = None


def _get_reader():
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(["en"], gpu=False)
    return _reader


# ── Dimension text parsing ────────────────────────────────────────────
# Matches a feet[-inches] measurement: 40'  15'-0"  12'-8"  16'-4
_FEET_RE = re.compile(r"(\d+)\s*'\s*(?:-?\s*(\d+)\s*\"?)?")


def _parse_feet(part: str) -> Optional[float]:
    """'12\'-8\"' → 12.667 ft, '40\'' → 40.0. None if no feet value."""
    m = _FEET_RE.search(part)
    if not m:
        return None
    feet = int(m.group(1))
    inches = int(m.group(2)) if m.group(2) else 0
    return round(feet + inches / 12.0, 3)


def _parse_dim_token(text: str) -> list[float]:
    """Parse a dimension label into 1 (single) or 2 (WxH pair) feet values."""
    parts = re.split(r"[xX]", text)
    vals = [v for v in (_parse_feet(p) for p in parts) if v is not None]
    return vals


def extract_dimensions(image_path: str) -> list[dict]:
    """OCR the plan and return parsed dimension tokens with positions."""
    reader = _get_reader()
    tokens = []
    for box, text, conf in reader.readtext(image_path):
        vals = _parse_dim_token(text)
        if not vals:
            continue
        cx = int(sum(p[0] for p in box) / 4)
        cy = int(sum(p[1] for p in box) / 4)
        tokens.append({
            "text": text.strip(),
            "values_ft": vals,
            "center": (cx, cy),
            "conf": round(float(conf), 2),
            "is_pair": len(vals) == 2,
        })
    return tokens


# ── Scale calibration ─────────────────────────────────────────────────
def _room_at(cx, cy, rooms):
    """Return the detected room whose bbox contains point (cx, cy)."""
    for room in rooms:
        b = room["bbox"]
        if b["x"] <= cx <= b["x"] + b["w"] and b["y"] <= cy <= b["y"] + b["h"]:
            return room
    return None


# A scale is only trusted when independent samples corroborate each other.
# Getting this wrong is worse than reporting nothing: the 3D stage sizes the
# whole world from this number, so a 2x error turns a flat into a cathedral,
# and it fails silently (the walkthrough still "works", just wrong).
_MIN_SAMPLES = 2
_MAX_DEVIATION = 0.35      # sample vs median, before it is discarded
_MAX_SPREAD = 1.5          # surviving max/min ratio


def _calibrate(tokens, rooms, building_bbox) -> Optional[float]:
    """Feet-per-pixel from room-dim labels matched to room bboxes.

    Returns None unless several samples agree — a lone OCR read (or two that
    disagree) is noise, not a measurement. See _MIN_SAMPLES above.
    """
    samples = []       # feet-per-pixel estimates
    pair_samples = 0   # from room labels — the trustworthy kind
    for tok in tokens:
        if not tok["is_pair"]:
            continue
        room = _room_at(*tok["center"], rooms)
        if room is None:
            continue
        b = room["bbox"]
        px_long, px_short = max(b["w"], b["h"]), min(b["w"], b["h"])
        ft_long, ft_short = max(tok["values_ft"]), min(tok["values_ft"])
        if px_long > 0 and px_short > 0:
            samples.append(ft_long / px_long)
            samples.append(ft_short / px_short)
            pair_samples += 2

    # Extra sample: an overall single dimension vs the building width. Only
    # ever corroborating evidence — on its own it cannot establish the scale,
    # because a misread token ("ICv X 106'") is indistinguishable from a real
    # overall dimension and would set the scale for the entire model.
    if building_bbox is not None and pair_samples:
        bw = building_bbox[2] - building_bbox[0]
        singles = [t for t in tokens if not t["is_pair"]]
        # The overall width label sits near the top of the plan.
        top = sorted(singles, key=lambda t: t["center"][1])[:2]
        for t in top:
            if bw > 0 and t["values_ft"][0] > 20:  # overall dims are large
                samples.append(t["values_ft"][0] / bw)

    if len(samples) < _MIN_SAMPLES:
        return None

    median = float(np.median(samples))
    if median <= 0:
        return None
    # Drop outliers, then require what is left to actually agree.
    kept = [s for s in samples if abs(s - median) / median <= _MAX_DEVIATION]
    if len(kept) < _MIN_SAMPLES:
        return None
    if max(kept) / min(kept) > _MAX_SPREAD:
        return None
    return float(np.median(kept))


# ── Fallback scale: door widths ───────────────────────────────────────
# Doors are the most standardised thing on a floor plan, and the detector finds
# them reliably, so their pixel width calibrates the plan even when no printed
# dimension survives OCR. A standard interior door leaf is ~0.80 m (32").
# Back-solving the two sample plans that DO have trustworthy printed dimensions
# gave 0.77 m (3br CAD) and 0.79 m (cedreo apartment), so 0.80 is a good prior.
_STD_DOOR_M = 0.80
_M_PER_FT = 0.3048
_MIN_DOORS_FOR_SCALE = 2
# At least half the doors must agree with the median within this factor;
# otherwise "doors" are probably mis-detections of varying junk.
_DOOR_AGREE_TOL = 0.4
# A building this pipeline should ever see, in metres. Outside → don't guess.
_PLAUSIBLE_BUILDING_M = (3.0, 80.0)


def estimate_scale_from_doors(result: dict) -> Optional[float]:
    """Feet-per-pixel estimated from detected door widths, or None.

    This is an *estimate*, not a measurement — callers should mark it as such
    (see `scale_source` in main.run_detection). It exists because the 3D stage
    needs some physically-grounded metres-per-pixel: without it the app fell
    back to a flat 1px=1cm, which is purely a function of image resolution and
    made the same house 15.2 m wide at 2732px but 2.9 m wide at 447px.
    """
    doors = [float(o.get("width_px") or 0) for o in result.get("openings", [])
             if o.get("type") == "door"]
    doors = [d for d in doors if d > 0]
    if len(doors) < _MIN_DOORS_FOR_SCALE:
        return None

    median_px = float(np.median(doors))
    if median_px <= 0:
        return None
    agree = [d for d in doors if abs(d - median_px) / median_px <= _DOOR_AGREE_TOL]
    if len(agree) * 2 < len(doors):
        return None

    ft_per_px = (_STD_DOOR_M / float(np.median(agree))) / _M_PER_FT

    # Reject if the implied building is not a building.
    bbox = _building_bbox(result)
    if bbox is None:
        return None
    span_px = max(bbox[2] - bbox[0], bbox[3] - bbox[1])
    span_m = span_px * ft_per_px * _M_PER_FT
    if not (_PLAUSIBLE_BUILDING_M[0] <= span_m <= _PLAUSIBLE_BUILDING_M[1]):
        return None
    return ft_per_px


def _building_bbox(result):
    xs, ys = [], []
    for w in result["walls"]:
        xs += [w["x1"], w["x2"]]; ys += [w["y1"], w["y2"]]
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys))


def _wall_len_px(w):
    return float(np.hypot(w["x2"] - w["x1"], w["y2"] - w["y1"]))


# ── Public entry point ────────────────────────────────────────────────
def measure_floor_plan(result: dict, image_path: str) -> dict:
    """Augment a detection result (from detector or ml_detector) in place with
    real-world measurements. Returns the same dict with added fields and a
    `measurements` summary. If no scale can be found, sets scale to None and
    leaves geometry untouched (callers should handle a missing scale)."""
    tokens = extract_dimensions(image_path)
    bbox = _building_bbox(result)
    ft_per_px = _calibrate(tokens, result.get("rooms", []), bbox)

    result.setdefault("stats", {})
    result["stats"]["ocr_dimension_labels"] = len(tokens)
    result["stats"]["scale_ft_per_px"] = round(ft_per_px, 5) if ft_per_px else None

    if ft_per_px:
        apply_scale(result, ft_per_px)
        # Attach the OCR label whose text sits inside each room, if any.
        for room in result["rooms"]:
            for tok in tokens:
                if tok["is_pair"] and _room_at(*tok["center"], [room]):
                    room["label_dim"] = tok["text"]
                    room["label_dim_ft"] = tok["values_ft"]
                    break

    if bbox and ft_per_px:
        result.setdefault("measurements", {})["dimension_labels_read"] = [
            t["text"] for t in tokens
        ]
    return result


def apply_scale(result: dict, ft_per_px: float) -> dict:
    """Annotate walls/rooms with real-world sizes for a given feet-per-pixel.

    Shared by both scale sources (printed dimension labels and the door-width
    estimate) so the two produce identically-shaped output.
    """
    for w in result.get("walls", []):
        w["length_ft"] = round(_wall_len_px(w) * ft_per_px, 2)

    for room in result.get("rooms", []):
        b = room["bbox"]
        room["computed_dim_ft"] = [
            round(b["w"] * ft_per_px, 1), round(b["h"] * ft_per_px, 1)
        ]
        room["area_sqft"] = round(room["area"] * ft_per_px * ft_per_px, 1)

    bbox = _building_bbox(result)
    if bbox:
        m = result.setdefault("measurements", {})
        m["scale_ft_per_px"] = round(ft_per_px, 5)
        m["building_ft"] = [
            round((bbox[2] - bbox[0]) * ft_per_px, 1),
            round((bbox[3] - bbox[1]) * ft_per_px, 1),
        ]
    return result
