"""
ml_detector.py — CubiCasa5k-based floor-plan detection.

Runs the pretrained CubiCasa5k segmentation model (CPU) and returns the SAME
JSON schema as detector.detect_floor_plan, so the API / frontend / 3D stages
need no changes.

Strategy (primary path — junction-based):
  - Rotation-averaged inference (4×90°) → full 44-channel prediction.
  - CubiCasa's native post-processor (get_polygons) reads the model's wall-
    JUNCTION heatmaps and builds walls as a graph between those junctions, so
    walls share junctions and are gap-free by construction. Rooms come out as
    class-merged polygons; openings are snapped onto their host walls.
  - Out-of-building rooms (logos/legends) are dropped via the wall envelope.

Fallback path (skeleton): if post-processing fails or finds no walls, the wall
mask is skeletonized and vectorized (less accurate, but robust).

Both paths emit the SAME JSON schema as detector.detect_floor_plan (plus a
per-room `type` label), so the API / frontend / 3D stages need no changes.

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
_ICON_CLOSET = 3         # built-in closet/wardrobe icon
_ICON_TOILET = 5
_ICON_SINK = 6
_ICON_BATHTUB = 9
_BATH_FIXTURE_ICONS = (_ICON_TOILET, _ICON_SINK, _ICON_BATHTUB)

# Human-readable room labels (rooms channel), bonus over the classical path.
_ROOM_NAMES = [
    "background", "outdoor", "wall", "kitchen", "living_room", "bedroom",
    "bath", "entry", "railing", "storage", "garage", "undefined",
]
# Classes that count as real enclosed rooms (exclude bg/outdoor/wall/railing).
_ROOM_CLASSES = {3, 4, 5, 6, 7, 9, 10, 11}
# "Definite" room classes carry real semantic meaning; storage(9) and
# undefined(11) are the model's catch-all buckets. On noisy plans (rendered/
# colored, not clean CAD) the model scatters a lot of low-confidence
# undefined/storage pixels everywhere, which can outnumber a room's real
# class even when that real class is clearly the right answer — so the vote
# below checks definite classes FIRST and only falls back to the catch-all
# when no definite class has a meaningful share of the room.
_DEFINITE_ROOM_CLASSES = {3, 4, 5, 6, 7, 10}

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


# ══════════════════════════════════════════════════════════════════════
#  PRIMARY PATH — junction-based vectorization (CubiCasa post-processing)
#  The model predicts wall-junction heatmaps; CubiCasa's post-processor
#  builds walls as a graph between those junctions, so walls share
#  junctions and are gap-free by construction. Rotation-averaged inference
#  (4×90°) is the model's best-quality mode.
# ══════════════════════════════════════════════════════════════════════

_rotate = None
_scipy_patched = False


def _patch_scipy_mode():
    """CubiCasa's 2019 post-processing calls stats.mode(x).mode[0]; modern
    scipy returns a scalar mode. Restore the old array behavior."""
    global _scipy_patched
    if _scipy_patched:
        return
    import scipy.stats as sps
    _orig = sps.mode
    def _compat(a, *args, **kwargs):
        kwargs.setdefault("keepdims", True)
        return _orig(a, *args, **kwargs)
    sps.mode = _compat
    _scipy_patched = True


class _RotateNTurns:
    """Vendored from CubiCasa5k (augmentations.py) — rotates the image tensor
    and permutes the directional heatmap channels for test-time rotation
    averaging. Vendored to avoid the training-only loaders dependency chain."""
    def rot_tensor(self, t, n):
        if n == 1: t = t.flip(2).transpose(3, 2)
        elif n == -1: t = t.transpose(3, 2).flip(2)
        elif n == 2: t = t.flip(2).flip(3)
        return t

    def rot_points(self, t, n):
        s = t.clone().detach()
        if n == 1:
            s[:, 1]=t[:, 0]; s[:, 2]=t[:, 1]; s[:, 3]=t[:, 2]; s[:, 0]=t[:, 3]
            s[:, 5]=t[:, 4]; s[:, 6]=t[:, 5]; s[:, 7]=t[:, 6]; s[:, 4]=t[:, 7]
            s[:, 9]=t[:, 8]; s[:, 10]=t[:, 9]; s[:, 11]=t[:, 10]; s[:, 8]=t[:, 11]
            s[:, 15]=t[:, 13]; s[:, 16]=t[:, 14]; s[:, 14]=t[:, 15]; s[:, 13]=t[:, 16]
            s[:, 18]=t[:, 17]; s[:, 20]=t[:, 18]; s[:, 17]=t[:, 19]; s[:, 19]=t[:, 20]
        elif n == -1:
            s[:, 3]=t[:, 0]; s[:, 0]=t[:, 1]; s[:, 1]=t[:, 2]; s[:, 2]=t[:, 3]
            s[:, 7]=t[:, 4]; s[:, 4]=t[:, 5]; s[:, 5]=t[:, 6]; s[:, 6]=t[:, 7]
            s[:, 11]=t[:, 8]; s[:, 8]=t[:, 9]; s[:, 9]=t[:, 10]; s[:, 10]=t[:, 11]
            s[:, 16]=t[:, 13]; s[:, 15]=t[:, 14]; s[:, 13]=t[:, 15]; s[:, 14]=t[:, 16]
            s[:, 19]=t[:, 17]; s[:, 17]=t[:, 18]; s[:, 20]=t[:, 19]; s[:, 18]=t[:, 20]
        elif n == 2:
            s[:, 2]=t[:, 0]; s[:, 3]=t[:, 1]; s[:, 0]=t[:, 2]; s[:, 4]=t[:, 3]
            s[:, 6]=t[:, 4]; s[:, 7]=t[:, 5]; s[:, 4]=t[:, 6]; s[:, 5]=t[:, 7]
            s[:, 10]=t[:, 8]; s[:, 11]=t[:, 9]; s[:, 8]=t[:, 10]; s[:, 9]=t[:, 11]
            s[:, 14]=t[:, 13]; s[:, 13]=t[:, 14]; s[:, 16]=t[:, 15]; s[:, 15]=t[:, 16]
            s[:, 20]=t[:, 17]; s[:, 19]=t[:, 18]; s[:, 18]=t[:, 19]; s[:, 17]=t[:, 20]
        return s

    def __call__(self, x, kind, n):
        return self.rot_tensor(x, n) if kind == "tensor" else self.rot_points(x, n)


def _predict_full(img_bgr, max_dim=1024):
    """Rotation-averaged forward pass → full (1,44,H,W) prediction tensor and
    the working size (nw, nh)."""
    import torch
    import torch.nn.functional as F
    global _rotate
    if _rotate is None:
        _rotate = _RotateNTurns()

    model = load_ml_model()
    h, w = img_bgr.shape[:2]
    # Normalize toward the model's working resolution: UPSCALE small images up
    # to it (a low-res plan fed at native size under-detects), DOWNSCALE large
    # ones down to it. Experiments show ~1024px is the model's sweet spot —
    # going higher over-detects (false walls/openings) and is much slower.
    scale = max_dim / max(h, w)
    nw = max(32, int(round(w * scale / 32)) * 32)
    nh = max(32, int(round(h * scale / 32)) * 32)
    interp = cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA
    rgb = cv2.cvtColor(cv2.resize(img_bgr, (nw, nh), interpolation=interp),
                       cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    rgb = rgb * 2.0 - 1.0
    image = torch.from_numpy(np.moveaxis(rgb, -1, 0))[None]

    rotations = [(0, 0), (1, -1), (2, 2), (-1, 1)]
    preds = torch.zeros([len(rotations), _N_CLASSES, nh, nw])
    with torch.no_grad():
        for i, (fwd, back) in enumerate(rotations):
            r = _rotate(image, "tensor", fwd)
            p = model(r)
            p = _rotate(p, "tensor", back)
            p = _rotate(p, "points", back)
            p = F.interpolate(p, size=(nh, nw), mode="bilinear", align_corners=True)
            preds[i] = p[0]
    return torch.mean(preds, 0, True), (nw, nh)


def _wall_centerline(p):
    """4-corner wall polygon → (x1,y1,x2,y2, thickness) centerline.

    Uses the polygon's own minimum-area oriented rect rather than its
    axis-aligned bounding box. get_polygons() sometimes returns a wall quad
    that's slightly skewed near a junction (not a perfect rectangle); an
    axis-aligned bbox around a skewed quad is larger than the quad itself,
    which stretches the centerline past the wall's real endpoint into the
    next room — the "wall extends where it shouldn't" corner artifact.
    minAreaRect finds the quad's actual long axis, so the centerline only
    spans the wall's real footprint.
    """
    rect = cv2.minAreaRect(p.astype(np.float32))
    (cx, cy), (rw, rh), angle = rect
    if rw < rh:
        rw, rh = rh, rw
        angle += 90.0
    theta = math.radians(angle)
    hl = rw / 2.0
    dx, dy = math.cos(theta) * hl, math.sin(theta) * hl
    x1, y1 = cx - dx, cy - dy
    x2, y2 = cx + dx, cy + dy
    return int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2)), float(rh)


def _postprocess(prediction, nw, nh):
    """Run CubiCasa's junction post-processing → (walls, rooms, openings) as
    legacy-schema dicts at the working resolution. Raises on failure so the
    caller can fall back to the skeleton path."""
    _patch_scipy_mode()
    if _CUBI_DIR not in sys.path:
        sys.path.insert(0, _CUBI_DIR)
    from floortrans.post_prosessing import split_prediction, get_polygons

    heatmaps, rooms_seg, icons_seg = split_prediction(prediction, (nh, nw), [21, 12, 11])
    # Per-pixel argmax masks for room typing (see _rooms_from_geometry): the
    # boundary comes from OUR walls below, not from get_polygons' own
    # wall-junction grid (room_polys/room_types, intentionally unused here —
    # see the docstring on _rooms_from_geometry for why).
    rooms_pred = np.argmax(rooms_seg, axis=0)
    icons_pred = np.argmax(icons_seg, axis=0)
    polygons, types, _room_polys, _room_types = get_polygons(
        (heatmaps, rooms_seg, icons_seg), 0.2, [_ICON_WINDOW, _ICON_DOOR]
    )

    # ── Walls (centerlines + thickness), classified main/partition ──
    raw = [(_wall_centerline(polygons[i]), t.get("class"))
           for i, t in enumerate(types) if t["type"] == "wall"]
    raw = [r for r in raw if _len(r[0][0], r[0][1], r[0][2], r[0][3]) > 3]
    thicknesses = [r[0][4] for r in raw]
    seglist = [(r[0][0], r[0][1], r[0][2], r[0][3]) for r in raw]
    # get_polygons' wall quads are rarely exactly axis-aligned — even a degree
    # or two of tilt, combined with the frontend's fixed corner-fill extension
    # (SceneCanvas.jsx), shows up as a visible spike poking past a corner
    # where this wall meets a properly orthogonal neighbor. Snap near-axis
    # walls to exact 0°/90° (same as the skeleton fallback path already
    # does), then re-close any junction gaps the snap introduces.
    if seglist:
        heal_tol = max(14, min(nw, nh) // 40)
        seglist = _final_angle_snap(seglist, thresh=7)
        seglist = _heal_junctions(seglist, tol=heal_tol)
    _, wall_types = _classify_wall_types(seglist, thicknesses) if seglist else ([], [])
    walls = []
    for idx, (seg, _cls) in enumerate(raw):
        th = seg[4]
        x1, y1, x2, y2 = seglist[idx]
        walls.append({
            "id": f"wall_{idx}",
            "x1": x1, "y1": y1, "x2": x2, "y2": y2,
            "length": round(_len(x1, y1, x2, y2), 1),
            "angle": round(_angle_deg(x1, y1, x2, y2), 1),
            "wall_type": wall_types[idx] if idx < len(wall_types) else "partition",
            "thickness": round(th, 2),
        })

    # ── Rooms: boundaries from OUR walls (flood-fill), types from CubiCasa's
    # per-pixel predictions sampled inside each region. See
    # _rooms_from_geometry's docstring for why this replaced get_polygons'
    # own wall-junction room grid (it could merge two real rooms into one
    # blob whenever a partition wall's junction wasn't cleanly detected).
    rooms = _rooms_from_geometry(walls, rooms_pred, icons_pred, nw, nh)

    # ── Openings (icon polygons: window=1, door=2) → nearest wall ──
    openings = []
    oid = 0
    for i, t in enumerate(types):
        if t["type"] != "icon" or int(t.get("class", -1)) not in (_ICON_WINDOW, _ICON_DOOR):
            continue
        p = polygons[i]
        cx, cy = int(p[:, 0].mean()), int(p[:, 1].mean())
        w_px = float(max(p[:, 0].max() - p[:, 0].min(), p[:, 1].max() - p[:, 1].min()))
        openings.append({
            "id": f"opening_{oid}",
            "wall_id": _nearest_wall_id(cx, cy, walls),
            "x": cx, "y": cy,
            "width_px": w_px,
            "type": "door" if int(t["class"]) == _ICON_DOOR else "window",
        })
        oid += 1

    return walls, rooms, openings


def _predict_masks(img_bgr, max_dim=1024):
    """Run the model and return (rooms_pred, icons_pred) at the working scale,
    plus the scale factor back to original coordinates."""
    import torch
    import torch.nn.functional as F

    model = load_ml_model()
    h, w = img_bgr.shape[:2]
    # Normalize toward the working resolution (upscale small, downscale large).
    scale = max_dim / max(h, w)
    # Multiple of 32 for the hourglass down/up-sampling.
    nw = max(32, int(round(w * scale / 32)) * 32)
    nh = max(32, int(round(h * scale / 32)) * 32)

    resized = cv2.resize(img_bgr, (nw, nh),
                         interpolation=cv2.INTER_CUBIC if scale > 1.0 else cv2.INTER_AREA)
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
    # Close T-junction / corner gaps: extend endpoints to meet perpendicular
    # walls. Two passes at a slightly wider tolerance catch junctions that only
    # line up after a first round of extension.
    heal_tol = max(14, min(w, h) // 40)
    snapped = _heal_junctions(snapped, tol=heal_tol)
    snapped = _heal_junctions(snapped, tol=heal_tol)
    # Bridge collinear wall pieces separated by a gap (a wall broken into two
    # segments on the same line), then re-heal perpendicular junctions.
    snapped = _coaxial_merge(snapped, axis_tolerance=10, gap_tolerance=heal_tol * 2)
    snapped = _heal_junctions(snapped, tol=heal_tol)
    snapped = _snap_endpoints(snapped, snap_radius=12)

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


def _rooms_from_geometry(walls, rooms_pred, icons_pred, w, h):
    """Derive room BOUNDARIES from our own validated wall geometry, then read
    each room's TYPE off CubiCasa's per-pixel class + fixture-icon evidence.

    Why not trust CubiCasa's own room polygons directly (get_polygons /
    merge_rectangles): that grid is built from WALL-JUNCTION points, so a
    real partition wall whose junction wasn't cleanly detected (e.g. a short
    stub between a closet and a washroom) leaves no dividing grid line —
    the two genuinely separate rooms then merge into one oversized
    "undefined" polygon, and a room's own per-pixel class can also come out
    fragmented (furniture/occlusion) into several same-type polygons that
    should really be one room. Flood-filling OUR walls instead guarantees
    exactly one non-overlapping region per enclosed space, matching what the
    2D editor and the 3D model already treat as "a room" — geometry and
    semantics are decoupled: boundary comes from walls, label comes from a
    per-region majority vote (+ fixture-icon overrides) inside that boundary.
    """
    # A thin, FIXED sealing thickness — not each wall's real detected
    # thickness. This raster's only job is "is a wall here, for flood-fill
    # purposes"; it does not need to match real wall width. The 3D renderer
    # draws every wall at one flat thickness regardless of its detected
    # value, so carving room boundaries out of the (often much thicker, and
    # variable per-wall) detected thickness pulls the floor polygon back
    # well past where the rendered wall's inner face actually sits — a
    # visible gap between floor and wall in 3D. A thin, uniform seal keeps
    # the boundary right at the wall centerline instead, so the floor runs
    # under the wall's real footprint (invisible, since the wall covers it)
    # rather than stopping short of it.
    canvas = np.zeros((h, w), dtype=np.uint8)
    for wall in walls:
        cv2.line(canvas, (wall["x1"], wall["y1"]), (wall["x2"], wall["y2"]), 255, 5)

    # Moderate dilate + close: on harder (rendered/colored) plans a real
    # partition wall can still have a genuine few-pixel detection gap even
    # after junction healing, and cutting this too thin lets two real rooms
    # flood into one (worse than a slightly larger inset). This is a
    # deliberate middle ground — snugger than the original heavy seal, but
    # not so thin that a real gap goes unbridged.
    kd = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.dilate(canvas, kd, iterations=1)
    closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9)))

    inverted = cv2.bitwise_not(closed)
    n, labels, stats, cents = cv2.connectedComponentsWithStats(inverted, connectivity=8)

    min_area = w * h * 0.0015   # drop slivers/noise
    max_area = w * h * 0.82     # drop the outer background region
    margin = max(6, min(w, h) // 60)

    rooms = []
    rid = 0
    for lb in range(1, n):  # 0 = background label from connectedComponents
        area = float(stats[lb, cv2.CC_STAT_AREA])
        if area < min_area or area > max_area:
            continue
        x = int(stats[lb, cv2.CC_STAT_LEFT]); y = int(stats[lb, cv2.CC_STAT_TOP])
        rw = int(stats[lb, cv2.CC_STAT_WIDTH]); rh = int(stats[lb, cv2.CC_STAT_HEIGHT])
        # A region touching the image border is outside the building envelope.
        if x <= margin or y <= margin or (x + rw) >= w - margin or (y + rh) >= h - margin:
            continue

        region = labels == lb
        mask = region.astype(np.uint8) * 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = max(cnts, key=cv2.contourArea)
        approx = cv2.approxPolyDP(cnt, 0.01 * cv2.arcLength(cnt, True), True)
        if len(approx) < 3:
            continue

        # Base type: vote of the room-class prediction inside this exact
        # region, checking DEFINITE classes (kitchen/living/bedroom/bath/
        # entry/garage) first. On noisy (rendered/colored) plans the model
        # scatters undefined/storage pixels everywhere, and those catch-all
        # classes can out-count a real, clearly-correct class — so only fall
        # back to them when no definite class clears a low bar (~8% of the
        # region), rather than letting raw pixel count alone decide.
        classes, counts = np.unique(rooms_pred[region], return_counts=True)
        by_class = {int(c): int(n_) for c, n_ in zip(classes, counts)}
        valid_total = sum(n_ for c, n_ in by_class.items() if c in _ROOM_CLASSES)
        definite = [(c, n_) for c, n_ in by_class.items() if c in _DEFINITE_ROOM_CLASSES]
        best_definite = max(definite, key=lambda cc: cc[1]) if definite else None
        if best_definite and valid_total > 0 and best_definite[1] / valid_total >= 0.08:
            type_name = _ROOM_NAMES[best_definite[0]]
        else:
            catchall = [(c, n_) for c, n_ in by_class.items() if c in (9, 11)]
            if catchall:
                dominant = max(catchall, key=lambda cc: cc[1])[0]
                type_name = _ROOM_NAMES[dominant]
            else:
                type_name = "undefined"

        # Fixture-icon overrides: strong, direct evidence beats the coarse
        # per-pixel class vote (which frequently comes back "undefined" for
        # bathrooms/closets even though the fixtures are clearly present).
        region_icons = icons_pred[region]
        bath_px = int(np.count_nonzero(np.isin(region_icons, _BATH_FIXTURE_ICONS)))
        closet_px = int(np.count_nonzero(region_icons == _ICON_CLOSET))
        if bath_px > area * 0.015:
            type_name = "bath"
        elif closet_px > area * 0.12 and type_name in ("undefined", "storage"):
            type_name = "closet"

        rooms.append({
            "id": f"room_{rid}",
            "type": type_name,
            "area": round(area, 1),
            "bbox": {"x": x, "y": y, "w": rw, "h": rh},
            "centroid": {"x": int(cents[lb][0]), "y": int(cents[lb][1])},
            "polygon": [[int(p[0][0]), int(p[0][1])] for p in approx],
        })
        rid += 1

    rooms.sort(key=lambda r: r["area"], reverse=True)
    return rooms


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


def _scale_results(walls, rooms, openings, inv):
    """Scale all coordinates from working resolution back to original image."""
    if inv == 1.0:
        return walls, rooms, openings
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
    return walls, rooms, openings


def _detect_skeleton(img):
    """Fallback: mask-based skeleton vectorization (used if junction
    post-processing fails or returns nothing)."""
    rooms_pred, icons_pred, (pw, ph) = _predict_masks(img)
    opening_pixels = np.isin(icons_pred, [_ICON_WINDOW, _ICON_DOOR])
    wall_mask = ((rooms_pred == _WALL_CLASS) | opening_pixels).astype(np.uint8)
    walls = _walls_from_mask(wall_mask, pw, ph)
    rooms = _rooms_from_pred(rooms_pred, pw, ph)
    openings = _openings_from_masks(icons_pred, walls, pw, ph)
    return walls, rooms, openings, pw, ph


def detect_floor_plan_ml(image_path: str) -> dict[str, Any]:
    """CubiCasa-based detection. Returns the same schema as
    detector.detect_floor_plan (plus a per-room `type` label).

    Primary path uses the model's wall-junction heatmaps (get_polygons) for
    topologically-connected, gap-free walls. Falls back to the skeleton
    vectorizer if post-processing fails or finds no walls.
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")
    orig_h, orig_w = img.shape[:2]

    method = "junction"
    try:
        prediction, (pw, ph) = _predict_full(img)
        walls, rooms, openings = _postprocess(prediction, pw, ph)
        if not walls:
            raise ValueError("junction post-processing found no walls")
    except Exception as exc:
        method = f"skeleton_fallback ({type(exc).__name__})"
        walls, rooms, openings, pw, ph = _detect_skeleton(img)

    inv = orig_w / pw  # aspect preserved by multiple-of-32 rounding
    walls, rooms, openings = _scale_results(walls, rooms, openings, inv)

    stats = {
        "engine": "ml_cubicasa",
        "method": method,
        "image_size": {"width": orig_w, "height": orig_h},
        "processing_size": {"width": pw, "height": ph},
        "walls_final": len(walls),
        "rooms_detected": len(rooms),
        "openings_detected": len(openings),
        "doors": sum(1 for o in openings if o["type"] == "door"),
        "windows": sum(1 for o in openings if o["type"] == "window"),
        "closets": sum(1 for r in rooms if r["type"] == "closet"),
    }
    return {
        "image_size": {"width": orig_w, "height": orig_h},
        "walls": walls,
        "rooms": rooms,
        "openings": openings,
        "door_arcs": [],
        "stats": stats,
    }
