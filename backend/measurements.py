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


def _calibrate(tokens, rooms, building_bbox) -> Optional[float]:
    """Feet-per-pixel from room-dim labels matched to room bboxes (median)."""
    samples = []  # (feet, pixels)
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

    # Fallback / extra sample: an overall single dimension vs building width.
    if building_bbox is not None:
        bw = building_bbox[2] - building_bbox[0]
        singles = [t for t in tokens if not t["is_pair"]]
        # The overall width label sits near the top of the plan.
        top = sorted(singles, key=lambda t: t["center"][1])[:2]
        for t in top:
            if bw > 0 and t["values_ft"][0] > 20:  # overall dims are large
                samples.append(t["values_ft"][0] / bw)

    if not samples:
        return None
    return float(np.median(samples))


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
        for w in result["walls"]:
            w["length_ft"] = round(_wall_len_px(w) * ft_per_px, 2)

        for room in result["rooms"]:
            b = room["bbox"]
            room["computed_dim_ft"] = [
                round(b["w"] * ft_per_px, 1), round(b["h"] * ft_per_px, 1)
            ]
            room["area_sqft"] = round(room["area"] * ft_per_px * ft_per_px, 1)
            # Attach the OCR label whose text sits inside this room, if any.
            for tok in tokens:
                if tok["is_pair"] and _room_at(*tok["center"], [room]):
                    room["label_dim"] = tok["text"]
                    room["label_dim_ft"] = tok["values_ft"]
                    break

    if bbox and ft_per_px:
        result["measurements"] = {
            "scale_ft_per_px": round(ft_per_px, 5),
            "building_ft": [
                round((bbox[2] - bbox[0]) * ft_per_px, 1),
                round((bbox[3] - bbox[1]) * ft_per_px, 1),
            ],
            "dimension_labels_read": [t["text"] for t in tokens],
        }
    return result
