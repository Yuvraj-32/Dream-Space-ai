"""
ml_detector.py — CubiCasa5k-based floor-plan detection.

Runs the pretrained CubiCasa5k segmentation model (CPU) and returns the SAME
JSON schema as detector.detect_floor_plan, so the API / frontend / 3D stages
need no changes.

Strategy:
  - The model gives clean, furniture-free WALL / DOOR / WINDOW / ROOM pixel
    masks.
  - Walls: reuse detector.py's proven line-vectorization on the clean wall
    mask (it finally has clean input to work with) → segments in legacy form.
  - Rooms: connected components of the room-class mask → polygons, labeled by
    the model's room type (a capability the classical path never had).
  - Openings: door/window blobs → centroid + width, attached to nearest wall.

Model is loaded once (module singleton). Import is lazy-friendly: if torch or
the weights are missing, load_ml_model() raises and the API falls back to the
classical engine.
"""
import os
import sys
import math
from typing import Any

import cv2
import numpy as np

# Reuse the classical line-vectorization + wall classification helpers.
from detector import (
    _detect_lines, _merge_lines, _snap_endpoints, _final_angle_snap,
    _coaxial_merge, _remove_isolated, _get_wall_widths, _classify_wall_types,
    _len, _angle_deg,
)

_BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
_CUBI_DIR = os.path.join(_BACKEND_DIR, "ml", "CubiCasa5k")
_WEIGHTS = os.path.join(_BACKEND_DIR, "ml", "weights", "model_best_val_loss_var.pkl")

# CubiCasa output layout: 44 channels = 21 heatmaps + 12 rooms + 11 icons.
_N_CLASSES = 44
_ROOM_OFFSET = 21
_ICON_OFFSET = 21 + 12
_WALL_CLASS = 2          # in the room channel group
_ICON_WINDOW = 1         # in the icon channel group
_ICON_DOOR = 2
_ICON_CLOSET = 3         # built-in closet / wardrobe

# Human-readable room labels (rooms channel), bonus over the classical path.
_ROOM_NAMES = [
    "background", "outdoor", "wall", "kitchen", "living_room", "bedroom",
    "bath", "entry", "railing", "storage", "garage", "undefined",
]
# Classes that count as real enclosed rooms (exclude bg/outdoor/wall/railing).
_ROOM_CLASSES = {3, 4, 5, 6, 7, 9, 10, 11}

_model = None  # singleton


def load_ml_model():
    """Load the CubiCasa model once. Raises if torch or weights are missing."""
    global _model
    if _model is not None:
        return _model

    if not os.path.exists(_WEIGHTS):
        raise FileNotFoundError(
            f"CubiCasa weights not found at {_WEIGHTS}. "
            f"Download them into backend/ml/weights/ (see ML_UPGRADE_PLAN.md)."
        )
    import torch
    if _CUBI_DIR not in sys.path:
        sys.path.insert(0, _CUBI_DIR)
    from floortrans.models import get_model

    # get_model → init_weights() loads its backbone via a path relative to the
    # CubiCasa repo root, so build the model with that as the working dir.
    prev_cwd = os.getcwd()
    try:
        os.chdir(_CUBI_DIR)
        model = get_model("hg_furukawa_original", 51)
    finally:
        os.chdir(prev_cwd)

    model.conv4_ = torch.nn.Conv2d(256, _N_CLASSES, bias=True, kernel_size=1)
    model.upsample = torch.nn.ConvTranspose2d(
        _N_CLASSES, _N_CLASSES, kernel_size=4, stride=4
    )
    # torch 2.6+ defaults weights_only=True, which rejects this 2019 checkpoint.
    checkpoint = torch.load(_WEIGHTS, map_location="cpu", weights_only=False)
    model.load_state_dict(checkpoint["model_state"])
    model.eval()
    _model = model
    return _model


def _predict_masks(img_bgr, max_dim=1024):
    """Run the model and return (rooms_pred, icons_pred) at the working scale,
    plus the scale factor back to original coordinates."""
    import torch
    import torch.nn.functional as F

    model = load_ml_model()
    h, w = img_bgr.shape[:2]
    scale = min(1.0, max_dim / max(h, w))
    # Multiple of 32 for the hourglass down/up-sampling.
    nw = max(32, int(round(w * scale / 32)) * 32)
    nh = max(32, int(round(h * scale / 32)) * 32)

    resized = cv2.resize(img_bgr, (nw, nh), interpolation=cv2.INTER_AREA)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = rgb * 2.0 - 1.0
    tensor = torch.from_numpy(np.moveaxis(rgb, -1, 0))[None]

    with torch.no_grad():
        pred = model(tensor)
        pred = F.interpolate(pred, size=(nh, nw), mode="bilinear", align_corners=True)

    rooms = F.softmax(pred[0, _ROOM_OFFSET:_ROOM_OFFSET + 12], 0).numpy()
    icons = F.softmax(pred[0, _ICON_OFFSET:], 0).numpy()
    rooms_pred = np.argmax(rooms, axis=0).astype(np.int32)
    icons_pred = np.argmax(icons, axis=0).astype(np.int32)
    return rooms_pred, icons_pred, (nw, nh)


def _heal_junctions(lines, tol=16):
    """Close T-junction and corner gaps by extending axis-aligned wall
    endpoints to meet nearby perpendicular walls.

    Floor-plan walls are horizontal/vertical after angle-snapping, so a
    horizontal wall's endpoint is snapped in X to a nearby vertical wall
    (when the vertical wall's Y-span reaches the endpoint), and a vertical
    wall's endpoint is snapped in Y to a nearby horizontal wall. This turns
    "almost touching" endpoints into exact junctions without moving walls
    off-axis.
    """
    L = [list(l) for l in lines]

    def orient(l):
        return 'h' if abs(l[3] - l[1]) <= abs(l[2] - l[0]) else 'v'

    hor = [i for i, l in enumerate(L) if orient(l) == 'h']
    ver = [i for i, l in enumerate(L) if orient(l) == 'v']

    # Horizontal endpoints → snap X to a nearby vertical wall.
    for i in hor:
        l = L[i]
        for ex in (0, 2):  # x1 at index 0, x2 at index 2
            px, py = l[ex], l[ex + 1]
            best, bd = None, tol
            for j in ver:
                vx = (L[j][0] + L[j][2]) / 2.0
                y0, y1 = min(L[j][1], L[j][3]), max(L[j][1], L[j][3])
                if abs(vx - px) <= bd and (y0 - tol) <= py <= (y1 + tol):
                    bd = abs(vx - px); best = vx
            if best is not None:
                l[ex] = int(round(best))

    # Vertical endpoints → snap Y to a nearby horizontal wall.
    for i in ver:
        l = L[i]
        for ey in (1, 3):  # y1 at index 1, y2 at index 3
            px, py = l[ey - 1], l[ey]
            best, bd = None, tol
            for j in hor:
                hy = (L[j][1] + L[j][3]) / 2.0
                x0, x1 = min(L[j][0], L[j][2]), max(L[j][0], L[j][2])
                if abs(hy - py) <= bd and (x0 - tol) <= px <= (x1 + tol):
                    bd = abs(hy - py); best = hy
            if best is not None:
                l[ey] = int(round(best))

    return [tuple(l) for l in L]


def _walls_from_mask(wall_mask, w, h):
    """Vectorize the clean wall mask into legacy wall dicts.

    The mask has thick filled wall strokes; running edge+Hough on those yields
    a double line per wall and loses interior partitions when merged. Instead
    we skeletonize to 1px centerlines (one line per wall, interior included),
    then run Hough + light merging/snapping. Thickness is recovered from the
    distance transform of the original filled mask.
    """
    from skimage.morphology import skeletonize

    mask = (wall_mask > 0).astype(np.uint8)
    # Close small gaps so strokes are continuous before thinning.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5)))

    skel = skeletonize(mask > 0).astype(np.uint8) * 255
    min_len = max(12, min(w, h) // 30)
    raw = cv2.HoughLinesP(skel, rho=1, theta=np.pi / 180, threshold=15,
                          minLineLength=min_len, maxLineGap=12)
    if raw is None:
        return []
    lines = [tuple(int(v) for v in s.flatten()) for s in raw]

    # Light consolidation — the skeleton lines are already thin & single.
    merged = _merge_lines(lines, angle_thresh=6, dist_thresh=10)
    snapped = _snap_endpoints(merged, snap_radius=12)
    snapped = _final_angle_snap(snapped, thresh=12)
    snapped = _coaxial_merge(snapped, axis_tolerance=8, gap_tolerance=25)
    # Close T-junction / corner gaps: extend endpoints to meet perpendicular walls.
    snapped = _heal_junctions(snapped, tol=max(12, min(w, h) // 55))
    snapped = _snap_endpoints(snapped, snap_radius=10)

    dist = cv2.distanceTransform(mask, cv2.DIST_L2, 5)
    widths = _get_wall_widths(snapped, dist)
    _, wall_types = _classify_wall_types(snapped, widths)

    walls = []
    for idx, (x1, y1, x2, y2) in enumerate(snapped):
        walls.append({
            "id": f"wall_{idx}",
            "x1": int(x1), "y1": int(y1), "x2": int(x2), "y2": int(y2),
            "length": round(_len(x1, y1, x2, y2), 1),
            "angle": round(_angle_deg(x1, y1, x2, y2), 1),
            "wall_type": wall_types[idx] if idx < len(wall_types) else "partition",
            "thickness": round(widths[idx], 2) if idx < len(widths) else 0,
        })
    return walls


def _rooms_from_pred(rooms_pred, w, h):
    """Connected components of room-class pixels → labeled room polygons."""
    room_area_min = w * h * 0.002
    room_mask = np.isin(rooms_pred, list(_ROOM_CLASSES)).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(room_mask, connectivity=8)

    rooms = []
    for lb in range(1, n):
        area = float(stats[lb, cv2.CC_STAT_AREA])
        if area < room_area_min:
            continue
        x = int(stats[lb, cv2.CC_STAT_LEFT]); y = int(stats[lb, cv2.CC_STAT_TOP])
        rw = int(stats[lb, cv2.CC_STAT_WIDTH]); rh = int(stats[lb, cv2.CC_STAT_HEIGHT])

        region = labels == lb
        # Majority room class → human-readable label.
        classes, counts = np.unique(rooms_pred[region], return_counts=True)
        dominant = int(classes[np.argmax(counts)])
        label_name = _ROOM_NAMES[dominant] if dominant < len(_ROOM_NAMES) else "room"

        mask = region.astype(np.uint8) * 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = max(cnts, key=cv2.contourArea)
        approx = cv2.approxPolyDP(cnt, 0.01 * cv2.arcLength(cnt, True), True)
        polygon = [[int(p[0][0]), int(p[0][1])] for p in approx]

        rooms.append({
            "id": f"room_{lb}",
            "type": label_name,
            "area": round(area, 1),
            "bbox": {"x": x, "y": y, "w": rw, "h": rh},
            "centroid": {"x": int(cents[lb][0]), "y": int(cents[lb][1])},
            "polygon": polygon,
        })
    rooms.sort(key=lambda r: r["area"], reverse=True)
    return rooms


def _nearest_wall_id(cx, cy, walls):
    best_id, best_d = None, float("inf")
    for wall in walls:
        d = _point_seg_dist(cx, cy, wall["x1"], wall["y1"], wall["x2"], wall["y2"])
        if d < best_d:
            best_d, best_id = d, wall["id"]
    return best_id


def _point_seg_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))


def _openings_from_masks(icons_pred, walls, w, h):
    """Door/window blobs → opening dicts attached to the nearest wall."""
    openings = []
    min_area = max(20, w * h * 0.00005)
    gid = 0
    for icon_class, otype in ((_ICON_DOOR, "door"), (_ICON_WINDOW, "window")):
        mask = (icons_pred == icon_class).astype(np.uint8)
        n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
        for lb in range(1, n):
            area = stats[lb, cv2.CC_STAT_AREA]
            if area < min_area:
                continue
            cx, cy = int(cents[lb][0]), int(cents[lb][1])
            bw = int(stats[lb, cv2.CC_STAT_WIDTH]); bh = int(stats[lb, cv2.CC_STAT_HEIGHT])
            openings.append({
                "id": f"opening_{gid}",
                "wall_id": _nearest_wall_id(cx, cy, walls),
                "x": cx, "y": cy,
                "width_px": float(max(bw, bh)),
                "type": otype,
            })
            gid += 1
    return openings


def _fixtures_from_pred(icons_pred, w, h):
    """Built-in fixtures (currently closets/wardrobes) from the icon channel.
    CubiCasa labels a built-in closet as its own icon class; freestanding
    furniture is NOT detected (and stays out of scope)."""
    min_area = w * h * 0.0006
    mask = (icons_pred == _ICON_CLOSET).astype(np.uint8)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(mask, connectivity=8)
    out = []
    for lb in range(1, n):
        area = float(stats[lb, cv2.CC_STAT_AREA])
        if area < min_area:
            continue
        x = int(stats[lb, cv2.CC_STAT_LEFT]); y = int(stats[lb, cv2.CC_STAT_TOP])
        rw = int(stats[lb, cv2.CC_STAT_WIDTH]); rh = int(stats[lb, cv2.CC_STAT_HEIGHT])
        m = (labels == lb).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        poly = []
        if cnts:
            cnt = max(cnts, key=cv2.contourArea)
            ap = cv2.approxPolyDP(cnt, 0.02 * cv2.arcLength(cnt, True), True)
            poly = [[int(p[0][0]), int(p[0][1])] for p in ap]
        out.append({
            "id": f"fixture_{lb}",
            "type": "closet",
            "area": round(area, 1),
            "bbox": {"x": x, "y": y, "w": rw, "h": rh},
            "centroid": {"x": int(cents[lb][0]), "y": int(cents[lb][1])},
            "polygon": poly,
        })
    return out


def _scale_results(walls, rooms, openings, fixtures, inv):
    """Scale all coordinates from working resolution back to original image."""
    if inv == 1.0:
        return walls, rooms, openings, fixtures
    for wl in walls:
        wl["x1"] = int(wl["x1"] * inv); wl["y1"] = int(wl["y1"] * inv)
        wl["x2"] = int(wl["x2"] * inv); wl["y2"] = int(wl["y2"] * inv)
        wl["length"] = round(wl["length"] * inv, 1)
        wl["thickness"] = round(wl["thickness"] * inv, 2)
    for rm in rooms:
        rm["area"] = round(rm["area"] * inv * inv, 1)
        rm["bbox"] = {k: int(v * inv) for k, v in rm["bbox"].items()}
        rm["centroid"] = {k: int(v * inv) for k, v in rm["centroid"].items()}
        rm["polygon"] = [[int(x * inv), int(y * inv)] for x, y in rm["polygon"]]
    for op in openings:
        op["x"] = int(op["x"] * inv); op["y"] = int(op["y"] * inv)
        op["width_px"] = round(op["width_px"] * inv, 1)
    for fx in fixtures:
        fx["area"] = round(fx["area"] * inv * inv, 1)
        fx["bbox"] = {k: int(v * inv) for k, v in fx["bbox"].items()}
        fx["centroid"] = {k: int(v * inv) for k, v in fx["centroid"].items()}
        fx["polygon"] = [[int(x * inv), int(y * inv)] for x, y in fx["polygon"]]
    return walls, rooms, openings, fixtures


def detect_floor_plan_ml(image_path: str) -> dict[str, Any]:
    """CubiCasa-based detection. Returns the same schema as
    detector.detect_floor_plan (plus a per-room `type` label)."""
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    orig_h, orig_w = img.shape[:2]

    rooms_pred, icons_pred, (pw, ph) = _predict_masks(img)
    inv = orig_w / pw  # uniform scale (aspect preserved by multiple-of-32 rounding)

    # Vectorize walls from the wall class UNIONED with door/window pixels.
    # CubiCasa labels a window/door as its own class, leaving a gap in the raw
    # wall mask at every opening — which fragments or drops wall segments near
    # windows. An opening is still part of the wall line (just a cut in it), so
    # bridging the gaps yields continuous walls. Openings are still detected
    # separately below from the icon channels.
    opening_pixels = np.isin(icons_pred, [_ICON_WINDOW, _ICON_DOOR])
    wall_mask = ((rooms_pred == _WALL_CLASS) | opening_pixels).astype(np.uint8)
    walls = _walls_from_mask(wall_mask, pw, ph)
    rooms = _rooms_from_pred(rooms_pred, pw, ph)
    openings = _openings_from_masks(icons_pred, walls, pw, ph)
    fixtures = _fixtures_from_pred(icons_pred, pw, ph)
    walls, rooms, openings, fixtures = _scale_results(walls, rooms, openings, fixtures, inv)

    stats = {
        "engine": "ml_cubicasa",
        "image_size": {"width": orig_w, "height": orig_h},
        "processing_size": {"width": pw, "height": ph},
        "walls_final": len(walls),
        "rooms_detected": len(rooms),
        "openings_detected": len(openings),
        "doors": sum(1 for o in openings if o["type"] == "door"),
        "windows": sum(1 for o in openings if o["type"] == "window"),
        "fixtures_detected": len(fixtures),
    }
    return {
        "image_size": {"width": orig_w, "height": orig_h},
        "walls": walls,
        "rooms": rooms,
        "openings": openings,
        "fixtures": fixtures,
        "door_arcs": [],
        "stats": stats,
    }
