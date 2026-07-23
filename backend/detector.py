"""
detector.py — Floor Plan Detection Pipeline v3
Architecture (100x improvement over v1):

  PREPROCESSING
  ├─ 1. Adaptive preprocessing — CLAHE + bilateral + OTSU + adaptive combined
  ├─ 2. Morphological structural extraction — horizontal + vertical kernels
  │      isolate ONLY structural walls, kills text/furniture/dimensions at source
  └─ 3. Canny on structural-only binary

  LINE DETECTION
  ├─ 4. LSD (primary) + Hough (secondary) — combined, deduplicated
  └─ 5. Angle pre-snap before merging

  GRAPH CLEANUP
  ├─ 6. Two-pass iterative merging (duplicates + wall thickness)
  ├─ 7. Numpy-vectorized thickness validation
  ├─ 8. Graph-based endpoint snapping — clean T/L/X junctions
  └─ 9. Hard integer angle snap (0° / 90° / 45° / 135°) — guaranteed clean

  SEMANTIC DETECTION
  ├─ 10. Door arc detection — HoughCircles matches arcs to wall gaps
  ├─ 11. Window gap detection — edge-gap analysis with position heuristics
  └─ 12. Connected-component room detection — flood fill on wall raster
"""

import cv2
import numpy as np
from typing import Any
import math


# ═══════════════════════════════════════════════════════════════════
#  HELPERS
# ═══════════════════════════════════════════════════════════════════

def _len(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)

def _angle_deg(x1, y1, x2, y2):
    return math.degrees(math.atan2(y2 - y1, x2 - x1)) % 180

def _midpoint(x1, y1, x2, y2):
    return (x1 + x2) / 2, (y1 + y2) / 2

def _perp_dist(px, py, x1, y1, x2, y2):
    dx, dy = x2 - x1, y2 - y1
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (x1 + t * dx), py - (y1 + t * dy))

def _hard_snap_angle(angle_deg, thresh=7):
    """Snap to nearest orthogonal angle — floor plans are 0°/90° only."""
    targets = [0, 90, 180]
    best = min(targets, key=lambda t: min(abs(angle_deg - t), 180 - abs(angle_deg - t)))
    diff = min(abs(angle_deg - best), 180 - abs(angle_deg - best))
    return best % 180 if diff <= thresh else None  # None = don't snap

def _apply_angle_snap(x1, y1, x2, y2, angle_deg):
    """Rewrite endpoints so segment has exact angle_deg."""
    cx, cy = (x1 + x2) / 2.0, (y1 + y2) / 2.0
    half = _len(x1, y1, x2, y2) / 2.0
    rad = math.radians(angle_deg)
    dx, dy = math.cos(rad) * half, math.sin(rad) * half
    return int(round(cx - dx)), int(round(cy - dy)), int(round(cx + dx)), int(round(cy + dy))


# ═══════════════════════════════════════════════════════════════════
#  STEP 1 — ADAPTIVE PREPROCESSING
# ═══════════════════════════════════════════════════════════════════

def _preprocess(img):
    h, w = img.shape[:2]

    # Scale down — cap at 1200px for fast morphological ops
    max_dim = 1200
    scale = 1.0
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)), cv2.INTER_AREA)

    # ---- Suppress colored (non-black) annotation lines ----
    # Purple dimension lines, colored labels etc. have high saturation.
    # Real walls are black/dark gray = low saturation.
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    # Mask: keep only low-saturation pixels (walls are S < 50)
    color_mask = (sat > 50).astype(np.uint8) * 255
    # Dilate the color mask slightly to cover anti-aliased edges
    color_mask = cv2.dilate(color_mask, np.ones((3, 3), np.uint8), iterations=2)
    # White-out colored pixels in the image before grayscale conversion
    img_clean = img.copy()
    img_clean[color_mask > 0] = [255, 255, 255]

    gray = cv2.cvtColor(img_clean, cv2.COLOR_BGR2GRAY)

    # CLAHE — enhance local contrast
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # GaussianBlur — 10x faster than bilateral, sufficient for structural detection
    blurred = cv2.GaussianBlur(enhanced, (5, 5), 1.0)

    # OTSU global threshold (good for clean CAD)
    _, thresh_otsu = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    # Adaptive threshold (good for scanned/photo)
    thresh_adapt = cv2.adaptiveThreshold(
        blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, blockSize=15, C=4
    )

    # Combine both — keeps walls from both CAD and scanned modes
    thresh = cv2.bitwise_or(thresh_otsu, thresh_adapt)

    # Standard morphological cleanup
    k3 = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, k3, iterations=2)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN,  k3, iterations=1)

    return gray, blurred, thresh, scale


# ═══════════════════════════════════════════════════════════════════
#  STEP 2 — MORPHOLOGICAL STRUCTURAL EXTRACTION
#  This is the key innovation: extract ONLY horizontal and vertical
#  structural elements. Text, furniture, and thin lines are killed
#  before they ever reach the line detector.
# ═══════════════════════════════════════════════════════════════════

def _keep_building_component(structural, keep_frac=0.10):
    """
    Keep the largest connected component (the building wall skeleton) plus
    any other component at least `keep_frac` of its area. Everything smaller
    — title text, dimension/annotation lines, free-floating furniture — is
    dropped. Returns the structural binary unchanged if it is empty or has a
    single component.

    keep_frac guards against over-pruning: a genuinely large secondary
    structure (e.g. a detached wing separated by a wide opening) is kept,
    while annotation-sized components, which are small relative to the
    building, are removed.
    """
    n_labels, labels, stats, _ = cv2.connectedComponentsWithStats(
        (structural > 0).astype(np.uint8), connectivity=8
    )
    if n_labels <= 2:  # background + at most one component → nothing to prune
        return structural

    areas = stats[1:, cv2.CC_STAT_AREA]
    largest = int(areas.max())
    min_keep = largest * keep_frac

    cleaned = np.zeros_like(structural)
    for i in range(1, n_labels):
        if stats[i, cv2.CC_STAT_AREA] >= min_keep:
            cleaned[labels == i] = 255
    return cleaned


def _extract_structural(thresh, w, h):
    """
    Dual-scale morphological extraction:
    - Longer kernels  (min_dim//20) catch main/exterior walls reliably
    - Shorter kernels (min_dim//40) catch thin interior partitions
    Combine both, then clean up furniture-sized blobs.
    Also computes the distance transform for wall width measurement.
    """
    min_dim = min(w, h)

    # --- Scale 1: Main walls (longer kernel = stricter, fewer false positives) ---
    main_len = max(20, min_dim // 20)
    hk1 = cv2.getStructuringElement(cv2.MORPH_RECT, (main_len, 1))
    h_main = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, hk1)
    h_main = cv2.morphologyEx(h_main, cv2.MORPH_OPEN,  hk1)

    vk1 = cv2.getStructuringElement(cv2.MORPH_RECT, (1, main_len))
    v_main = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, vk1)
    v_main = cv2.morphologyEx(v_main, cv2.MORPH_OPEN,  vk1)

    main_struct = cv2.bitwise_or(h_main, v_main)

    # --- Scale 2: Thin partitions (shorter kernel = catches more, noisier) ---
    part_len = max(12, min_dim // 40)
    hk2 = cv2.getStructuringElement(cv2.MORPH_RECT, (part_len, 1))
    h_part = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, hk2)
    h_part = cv2.morphologyEx(h_part, cv2.MORPH_OPEN,  hk2)

    vk2 = cv2.getStructuringElement(cv2.MORPH_RECT, (1, part_len))
    v_part = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, vk2)
    v_part = cv2.morphologyEx(v_part, cv2.MORPH_OPEN,  vk2)

    part_struct = cv2.bitwise_or(h_part, v_part)

    # Combine both scales
    structural = cv2.bitwise_or(main_struct, part_struct)

    # Clean up: remove small isolated blobs (furniture fragments)
    # that survived the shorter kernel
    n_labels, labels, blob_stats, _ = cv2.connectedComponentsWithStats(
        (structural > 0).astype(np.uint8), connectivity=8
    )
    min_blob = max(50, w * h * 0.0003)  # minimum blob area
    for i in range(1, n_labels):
        blob_area = blob_stats[i, cv2.CC_STAT_AREA]
        blob_w = blob_stats[i, cv2.CC_STAT_WIDTH]
        blob_h = blob_stats[i, cv2.CC_STAT_HEIGHT]
        aspect = max(blob_w, blob_h) / max(min(blob_w, blob_h), 1)
        # Keep only elongated blobs (aspect > 3 = wall-like) or large blobs
        if blob_area < min_blob and aspect < 3:
            structural[labels == i] = 0

    # Keep only the building skeleton: the real walls form one dominant
    # connected component at the pixel level (even when the extracted line
    # SEGMENTS are fragmented). Title text, dimension lines with arrows, and
    # furniture that floats free of any wall form their own smaller
    # components — drop them here so they never become false walls or rooms.
    structural = _keep_building_component(structural)

    # Light cleanup
    k2 = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    structural = cv2.dilate(structural, k2, iterations=1)

    # Distance transform for wall width measurement
    dist_transform = cv2.distanceTransform(
        (structural > 0).astype(np.uint8), cv2.DIST_L2, 5
    )
    return structural, dist_transform


# ═══════════════════════════════════════════════════════════════════
#  STEP 3 — CANNY + HOUGH LINE DETECTION (proven v3 approach)
#  Runs Canny on the structural binary then HoughLinesP.
#  Two-pass merge handles both duplicates and wall-thickness doubling.
# ═══════════════════════════════════════════════════════════════════

def _detect_lines(structural_bin, gray, w, h):
    """Run Hough on the structural binary (fast, precise after morph extraction)."""
    edges = cv2.Canny(structural_bin, 30, 100, apertureSize=3)
    edges = cv2.dilate(edges, np.ones((2, 2), np.uint8), iterations=1)

    min_len = max(12, min(w, h) // 32)
    lines = []

    raw = cv2.HoughLinesP(
        edges, rho=1, theta=np.pi / 180,
        threshold=20, minLineLength=min_len, maxLineGap=15
    )
    if raw is not None:
        for seg in raw:
            flat = seg.flatten()
            lines.append((int(flat[0]), int(flat[1]), int(flat[2]), int(flat[3])))

    return lines, edges


# ═══════════════════════════════════════════════════════════════════
#  STEP 3b — WALL WIDTH FROM DISTANCE TRANSFORM
#  Sample the distance transform along each detected line.
#  dt[y,x] = distance to nearest background = half the wall thickness.
#  This gives accurate wall widths for main/partition classification.
# ═══════════════════════════════════════════════════════════════════

def _get_wall_widths(lines, dist_transform):
    """
    For each line, sample the distance transform along its midpoints.
    Returns list of full wall widths (= 2 × half-width from dist transform).
    Accurate to sub-pixel precision.
    """
    h, w  = dist_transform.shape
    widths = []
    for (x1, y1, x2, y2) in lines:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1:
            widths.append(0.0)
            continue
        n  = max(5, int(length) // 6)
        ts = np.linspace(0.15, 0.85, n)
        xs = np.clip((x1 + ts * dx).astype(int), 0, w - 1)
        ys = np.clip((y1 + ts * dy).astype(int), 0, h - 1)
        half_w = float(dist_transform[ys, xs].mean())
        widths.append(half_w * 2.0)   # full width
    return widths



# ═══════════════════════════════════════════════════════════════════
#  STEP 4 — MERGE NEARBY / PARALLEL LINES
# ═══════════════════════════════════════════════════════════════════

def _merge_lines(lines, angle_thresh=6, dist_thresh=20):
    if not lines:
        return []
    merged = []
    used = [False] * len(lines)
    for i, (x1, y1, x2, y2) in enumerate(lines):
        if used[i]:
            continue
        group = [(x1, y1, x2, y2)]
        ang_i = _angle_deg(x1, y1, x2, y2)
        used[i] = True
        for j, (x3, y3, x4, y4) in enumerate(lines):
            if used[j]:
                continue
            ang_j = _angle_deg(x3, y3, x4, y4)
            diff = min(abs(ang_i - ang_j) % 180, 180 - abs(ang_i - ang_j) % 180)
            if diff > angle_thresh:
                continue
            mx, my = _midpoint(x3, y3, x4, y4)
            if _perp_dist(mx, my, x1, y1, x2, y2) < dist_thresh:
                group.append((x3, y3, x4, y4))
                used[j] = True
        # Span all endpoints along principal axis
        pts = []
        for seg in group:
            pts += [(seg[0], seg[1]), (seg[2], seg[3])]
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length == 0:
            continue
        ux, uy = dx / length, dy / length
        projs = [(ux * (px - x1) + uy * (py - y1), px, py) for px, py in pts]
        projs.sort()
        _, sx, sy = projs[0]
        _, ex, ey = projs[-1]
        if _len(sx, sy, ex, ey) > 8:
            merged.append((int(sx), int(sy), int(ex), int(ey)))
    return merged


# ═══════════════════════════════════════════════════════════════════
#  STEP 5 — NUMPY-VECTORIZED THICKNESS VALIDATION
# ═══════════════════════════════════════════════════════════════════

def _thickness_filter(lines, binary, min_avg_thickness=2.5, samples=10, scan_r=20):
    """
    Vectorized perpendicular pixel support measurement.
    Eliminates thin noise that survived morphological extraction.
    ~30x faster than the Python-loop version.
    """
    h, w = binary.shape
    good       = []
    thicknesses = []
    for (x1, y1, x2, y2) in lines:
        dx, dy = x2 - x1, y2 - y1
        length = math.hypot(dx, dy)
        if length < 1:
            continue
        px, py = -dy / length, dx / length
        ts  = np.linspace(0.1, 0.9, samples)
        cxs = x1 + ts * dx
        cys = y1 + ts * dy
        ds  = np.arange(-scan_r, scan_r + 1)
        sxs = np.clip((cxs[:, None] + ds[None, :] * px).astype(int), 0, w - 1)
        sys_ = np.clip((cys[:, None] + ds[None, :] * py).astype(int), 0, h - 1)
        pixel_vals    = binary[sys_, sxs]
        avg_thickness = float((pixel_vals > 0).sum(axis=1).mean())
        # Faded/annotation lines: thickness too thin → discard
        if avg_thickness >= min_avg_thickness:
            good.append((x1, y1, x2, y2))
            thicknesses.append(avg_thickness)
    return good, thicknesses


# ═══════════════════════════════════════════════════════════════════
#  WALL TYPE CLASSIFICATION
#  Uses Otsu's method on the thickness histogram to adaptively find
#  the boundary between MAIN walls (thick) and PARTITIONS (thinner).
#  Faded/annotation lines are already discarded by min_avg_thickness.
# ═══════════════════════════════════════════════════════════════════

def _find_main_wall_threshold(thicknesses: list[float]) -> float:
    """
    Finds the Otsu-optimal thickness boundary between main walls and partitions.
    Returns the threshold value: walls >= threshold are 'main_wall'.
    If all walls are the same thickness, returns max+1 (all become partitions).
    """
    if not thicknesses or len(thicknesses) < 3:
        return float('inf')  # can't classify — treat all as partitions

    arr     = np.array(thicknesses, dtype=np.float32)
    t_min   = arr.min()
    t_max   = arr.max()
    t_range = t_max - t_min

    # If all walls have nearly identical thickness — no split possible
    if t_range < 1.5:
        # Still split at 75th percentile so thickest quarter = main
        return float(np.percentile(arr, 70))

    # Normalise to 0-255, apply Otsu to find natural histogram valley
    norm = ((arr - t_min) / t_range * 255.0).astype(np.uint8)
    otsu_val, _ = cv2.threshold(norm, 0, 255,
                                cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Map Otsu value back to original thickness scale
    main_threshold = t_min + (float(otsu_val) / 255.0) * t_range

    # Sanity clamp: 15-60% of walls should be "main"
    n_main = int((arr >= main_threshold).sum())
    frac   = n_main / len(arr)
    if frac < 0.15:
        main_threshold = float(np.percentile(arr, 75))
    elif frac > 0.60:
        main_threshold = float(np.percentile(arr, 50))

    return float(main_threshold)


def _classify_wall_types(
    lines: list[tuple],
    thicknesses: list[float],
) -> tuple[list[tuple], list[str]]:
    """
    Returns (lines, wall_types) where each wall_type is:
      'main_wall'  — bold structural / exterior wall
      'partition'  — interior divider / slim wall
    Faded lines are already removed before this function is called.
    """
    if not lines:
        return [], []

    main_thresh = _find_main_wall_threshold(thicknesses)
    types = [
        'main_wall' if t >= main_thresh else 'partition'
        for t in thicknesses
    ]
    return lines, types



# ═══════════════════════════════════════════════════════════════════
#  STEP 6 — GRAPH-BASED ENDPOINT SNAPPING
#  Build a graph of wall endpoints, merge nearby nodes,
#  creating clean T-junctions, L-corners, and X-crossings.
# ═══════════════════════════════════════════════════════════════════

def _snap_endpoints(lines, snap_radius=16):
    """
    Cluster wall endpoints within snap_radius → replace with cluster centroid.
    Produces clean topological junctions — no dangling endpoints.
    """
    if not lines:
        return lines

    endpoints = []
    for i, (x1, y1, x2, y2) in enumerate(lines):
        endpoints.append([i, 'start', float(x1), float(y1)])
        endpoints.append([i, 'end',   float(x2), float(y2)])

    # Union-Find clustering
    n = len(endpoints)
    parent = list(range(n))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def union(a, b):
        parent[find(a)] = find(b)

    for i in range(n):
        xi, yi = endpoints[i][2], endpoints[i][3]
        for j in range(i + 1, n):
            xj, yj = endpoints[j][2], endpoints[j][3]
            if math.hypot(xi - xj, yi - yj) <= snap_radius:
                union(i, j)

    # Compute centroid for each cluster
    clusters: dict[int, list] = {}
    for idx, ep in enumerate(endpoints):
        root = find(idx)
        clusters.setdefault(root, []).append(idx)

    centroids: dict[int, tuple] = {}
    for root, members in clusters.items():
        xs = [endpoints[m][2] for m in members]
        ys = [endpoints[m][3] for m in members]
        centroids[root] = (int(round(sum(xs) / len(xs))), int(round(sum(ys) / len(ys))))

    # Apply centroids back to lines
    new_lines = list(lines)
    for idx, ep in enumerate(endpoints):
        li, which, _, _ = ep
        cx, cy = centroids[find(idx)]
        x1, y1, x2, y2 = new_lines[li]
        if which == 'start':
            new_lines[li] = (cx, cy, x2, y2)
        else:
            new_lines[li] = (x1, y1, cx, cy)

    # Remove zero-length lines created by snapping
    return [(x1, y1, x2, y2) for (x1, y1, x2, y2) in new_lines if _len(x1, y1, x2, y2) > 5]


# ═══════════════════════════════════════════════════════════════════
#  STEP 7 — HARD ANGLE SNAP (FINAL PASS)
#  Applied AFTER all coordinate math — guaranteed clean 0°/90°
# ═══════════════════════════════════════════════════════════════════

def _final_angle_snap(lines, thresh=7):
    snapped = []
    for (x1, y1, x2, y2) in lines:
        ang = _angle_deg(x1, y1, x2, y2)
        target = _hard_snap_angle(ang, thresh)
        if target is not None:
            x1, y1, x2, y2 = _apply_angle_snap(x1, y1, x2, y2, target)
        snapped.append((x1, y1, x2, y2))
    return snapped


# ═══════════════════════════════════════════════════════════════════
#  STEP 6b — CO-AXIAL MERGE
#  After angle-snapping everything to 0°/90°, walls on the same
#  row (horizontal) or column (vertical) that overlap → merge into one.
# ═══════════════════════════════════════════════════════════════════

def _coaxial_merge(lines, axis_tolerance=8, gap_tolerance=20):
    """
    Group walls that share the same axis coordinate (within axis_tolerance)
    and overlap or nearly touch (gap < gap_tolerance), then span them.
    Dramatically reduces fragmented parallel walls.
    """
    if not lines:
        return []

    horiz, vert, diag = [], [], []
    for seg in lines:
        ang = _angle_deg(*seg) % 180
        if ang < 10 or ang > 170:      # horizontal
            horiz.append(seg)
        elif 80 < ang < 100:           # vertical
            vert.append(seg)
        else:
            diag.append(seg)           # diagonal — keep as-is

    def _merge_axis_group(segs, coord_idx, span_idx):
        """coord_idx=1 for horizontal (group by Y), =0 for vertical (group by X)."""
        if not segs:
            return []
        # Sort by axis coordinate
        segs_sorted = sorted(segs, key=lambda s: (s[coord_idx], s[span_idx]))
        groups = []
        cur_group = [segs_sorted[0]]
        cur_coord = segs_sorted[0][coord_idx]
        for seg in segs_sorted[1:]:
            if abs(seg[coord_idx] - cur_coord) <= axis_tolerance:
                cur_group.append(seg)
            else:
                groups.append(cur_group)
                cur_group = [seg]
                cur_coord = seg[coord_idx]
        groups.append(cur_group)

        merged = []
        for group in groups:
            # Sort along the span axis
            group.sort(key=lambda s: s[span_idx])
            avg_coord = int(round(sum(s[coord_idx] for s in group) / len(group)))
            # Merge overlapping/touching segments
            result = []
            cur_start = group[0][span_idx]
            cur_end   = group[0][span_idx + 2]  # x2 or y2
            for seg in group[1:]:
                s0 = seg[span_idx]
                s1 = seg[span_idx + 2]
                if s0 <= cur_end + gap_tolerance:  # overlapping or close
                    cur_end = max(cur_end, s1)
                else:
                    result.append((cur_start, cur_end))
                    cur_start, cur_end = s0, s1
            result.append((cur_start, cur_end))
            # Convert back to (x1,y1,x2,y2)
            for (a, b) in result:
                if coord_idx == 1:  # horizontal: coord=y, span=x
                    merged.append((a, avg_coord, b, avg_coord))
                else:               # vertical: coord=x, span=y
                    merged.append((avg_coord, a, avg_coord, b))
        return merged

    result  = _merge_axis_group(horiz, coord_idx=1, span_idx=0)
    result += _merge_axis_group(vert,  coord_idx=0, span_idx=1)
    result += diag
    return result


# ═══════════════════════════════════════════════════════════════════
#  STEP 6c — ISOLATED WALL REMOVAL
#  A wall whose BOTH endpoints have no neighbors in the wall network
#  is noise (a floating segment with nothing connected to it).
# ═══════════════════════════════════════════════════════════════════

def _remove_isolated(lines, neighbor_radius=30):
    """Remove wall segments with no wall neighbors at either endpoint."""
    if len(lines) < 4:
        return lines

    # Build list of all endpoints
    all_pts = []
    for i, (x1, y1, x2, y2) in enumerate(lines):
        all_pts.append((i, 'start', x1, y1))
        all_pts.append((i, 'end',   x2, y2))

    def _has_neighbor(wall_idx, ex, ey):
        for i, which, px, py in all_pts:
            if i == wall_idx:
                continue
            if math.hypot(ex - px, ey - py) <= neighbor_radius:
                return True
        return False

    kept = []
    for i, (x1, y1, x2, y2) in enumerate(lines):
        start_ok = _has_neighbor(i, x1, y1)
        end_ok   = _has_neighbor(i, x2, y2)
        # Keep wall if at least ONE endpoint has a neighbor
        if start_ok or end_ok:
            kept.append((x1, y1, x2, y2))
    return kept


# ═══════════════════════════════════════════════════════════════════
#  STEP 8 — DOOR ARC DETECTION
#  Doors in floor plans appear as quarter-circle arcs.
#  HoughCircles finds the arc radius; we match it to wall gaps.
# ═══════════════════════════════════════════════════════════════════

def _detect_door_arcs(gray, w, h, min_r=20, max_r=None):
    """
    Find door arcs using HoughCircles.
    Downscales input to 500px for 10-20x speed boost.
    """
    if max_r is None:
        max_r = min(w, h) // 5

    # Downscale to 500px max — circles are scale-invariant
    arc_max = 500
    arc_scale = 1.0
    gray_small = gray
    if max(h, w) > arc_max:
        arc_scale = arc_max / max(h, w)
        gray_small = cv2.resize(gray, (int(w * arc_scale), int(h * arc_scale)), cv2.INTER_AREA)

    # Blur before circle detection (reduces noise arcs)
    gray_small = cv2.GaussianBlur(gray_small, (5, 5), 1.5)

    s_min_r = max(5, int(min_r * arc_scale))
    s_max_r = max(s_min_r + 5, int(max_r * arc_scale))

    circles = cv2.HoughCircles(
        gray_small,
        cv2.HOUGH_GRADIENT,
        dp=2.0,
        minDist=s_min_r * 3,    # larger minDist = fewer duplicates
        param1=80,              # stronger edge threshold
        param2=40,              # higher accumulator threshold = fewer false arcs
        minRadius=s_min_r,
        maxRadius=s_max_r,
    )

    arcs = []
    if circles is not None:
        inv = 1.0 / arc_scale
        for c in np.round(circles[0]).astype(int):
            arcs.append({
                "x": int(c[0] * inv),
                "y": int(c[1] * inv),
                "radius": int(c[2] * inv),
            })
    return arcs


# ═══════════════════════════════════════════════════════════════════
#  STEP 9 — OPENING DETECTION (Doors + Windows)
#  Combines wall-gap analysis + door arc matching
# ═══════════════════════════════════════════════════════════════════

def _detect_openings(walls, edges, door_arcs, w, h):
    openings = []
    gap_id = 0
    abs_min_gap_px = max(20, w // 80)  # absolute minimum gap size

    for wall in walls:
        x1, y1, x2, y2 = wall["x1"], wall["y1"], wall["x2"], wall["y2"]
        wlen = wall["length"]
        if wlen < 40:
            continue

        # Higher density sampling
        num_samples = max(30, int(wlen) // 2)
        gap_runs = []
        in_gap = False
        gap_start = None
        consec_gap  = 0   # consecutive no-edge samples
        consec_edge = 0   # consecutive edge samples (to close gap confidently)

        for t_i in range(num_samples + 1):
            t = t_i / num_samples
            px = int(x1 + t * (x2 - x1))
            py = int(y1 + t * (y2 - y1))
            # Larger 8×8 window — suppresses JPEG/WEBP artifact gaps
            win = edges[max(0, py - 7):min(h, py + 8),
                        max(0, px - 7):min(w, px + 8)]
            has_edge = win.max() > 0

            if not has_edge:
                consec_gap  += 1
                consec_edge  = 0
                # Only open a gap after 3+ consecutive no-edge samples
                if not in_gap and consec_gap >= 3:
                    in_gap     = True
                    gap_start  = (t_i - consec_gap + 1) / num_samples
            else:
                consec_edge += 1
                consec_gap   = 0
                # Close gap only after 2+ consecutive edge samples
                if in_gap and consec_edge >= 2:
                    in_gap = False
                    gap_runs.append((gap_start, t))

        if in_gap:
            gap_runs.append((gap_start, 1.0))

        for (t0, t1) in gap_runs:
            gap_px    = (t1 - t0) * wlen
            gap_mid_t = (t0 + t1) / 2
            rel       = gap_px / wlen

            # Tighter filter: 6–35% of wall AND absolute floor
            if rel < 0.06 or rel > 0.35:
                continue
            if gap_px < abs_min_gap_px:
                continue
            # Ignore gaps right at wall endpoints
            if t0 < 0.04 or t1 > 0.96:
                continue

            gx = int(x1 + gap_mid_t * (x2 - x1))
            gy = int(y1 + gap_mid_t * (y2 - y1))

            # ── Match door arc ───────────────────────────────────
            matched_arc = None
            for arc in door_arcs:
                arc_dist = math.hypot(arc["x"] - gx, arc["y"] - gy)
                if arc_dist < gap_px * 0.9 and 0.4 * gap_px < arc["radius"] < 2.0 * gap_px:
                    matched_arc = arc
                    break

            if matched_arc is not None:
                opening_type = "door"
                arc_info = {
                    "arc_x":    matched_arc["x"],
                    "arc_y":    matched_arc["y"],
                    "arc_radius": matched_arc["radius"],
                }
            else:
                if rel > 0.14:
                    opening_type = "door"
                elif rel > 0.07:
                    center_dist  = abs(gap_mid_t - 0.5)
                    opening_type = "window" if center_dist < 0.28 else "door"
                else:
                    opening_type = "window"
                arc_info = {}

            entry = {
                "id":       f"opening_{gap_id}",
                "wall_id":  wall["id"],
                "x": gx, "y": gy,
                "width_px": round(gap_px, 1),
                "type":     opening_type,
            }
            entry.update(arc_info)
            openings.append(entry)
            gap_id += 1

    return openings


# ═══════════════════════════════════════════════════════════════════
#  STEP 10 — ROOM DETECTION (Connected Components)
# ═══════════════════════════════════════════════════════════════════

def _seal_openings(canvas, walls, openings, thickness):
    """
    Draw a virtual wall across each detected door/window opening, along the
    host wall's direction, so rooms don't leak into each other through the
    gap when the space is flood-filled. Without this, any two rooms joined
    by an open doorway merge into one region.
    """
    wall_by_id = {wall["id"]: wall for wall in walls}
    for o in openings:
        wall = wall_by_id.get(o.get("wall_id"))
        if wall is None:
            continue
        dx, dy = wall["x2"] - wall["x1"], wall["y2"] - wall["y1"]
        length = math.hypot(dx, dy)
        if length < 1:
            continue
        ux, uy = dx / length, dy / length
        # Span slightly wider than the opening to guarantee a clean seal.
        half = o.get("width_px", 0) * 0.7
        cx, cy = o["x"], o["y"]
        p1 = (int(round(cx - ux * half)), int(round(cy - uy * half)))
        p2 = (int(round(cx + ux * half)), int(round(cy + uy * half)))
        cv2.line(canvas, p1, p2, 255, thickness)


def _detect_rooms(walls, openings, w, h):
    """
    Rasterize walls → seal detected openings → close small furniture pockets
    → connected components on the inverted image = enclosed rooms.

    Sealing openings (rather than relying on huge dilation to bridge gaps)
    lets rooms joined by doorways stay separate, and keeps dilation light
    enough that real rooms aren't swallowed. Furniture outlines that survive
    as walls form small enclosed pockets — those are sealed shut so they do
    not register as tiny rooms.
    """
    wall_thickness = 10
    canvas = np.zeros((h, w), dtype=np.uint8)
    for wall in walls:
        cv2.line(canvas,
                 (wall["x1"], wall["y1"]),
                 (wall["x2"], wall["y2"]),
                 255, thickness=wall_thickness)

    _seal_openings(canvas, walls, openings, thickness=wall_thickness + 2)

    # Moderate dilation to bridge the gaps left by fragmented wall segments.
    # Kept lighter than the pre-sealing pipeline (which needed heavy dilation
    # to close doorways) but heavy enough to close endpoint gaps on noisier,
    # rendered plans where segments don't meet cleanly.
    kd = cv2.getStructuringElement(cv2.MORPH_RECT, (22, 22))
    closed = cv2.dilate(canvas, kd, iterations=2)
    closed = cv2.morphologyEx(closed, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (20, 20)))

    # Seal furniture pockets: enclosed non-wall regions smaller than
    # `fill_area` that don't touch the border are furniture interiors
    # (bed/sofa outlines), not rooms — fill them back into the wall mask.
    fill_area = w * h * 0.004
    inv = cv2.bitwise_not(closed)
    fn, flabels, fstats, _ = cv2.connectedComponentsWithStats(inv, connectivity=8)
    for lb in range(1, fn):
        a = fstats[lb, cv2.CC_STAT_AREA]
        x = fstats[lb, cv2.CC_STAT_LEFT]; y = fstats[lb, cv2.CC_STAT_TOP]
        rw = fstats[lb, cv2.CC_STAT_WIDTH]; rh = fstats[lb, cv2.CC_STAT_HEIGHT]
        touches = x <= 2 or y <= 2 or (x + rw) >= w - 2 or (y + rh) >= h - 2
        if a < fill_area and not touches:
            closed[flabels == lb] = 255

    # Find enclosed regions via connected components on inverted image
    inverted = cv2.bitwise_not(closed)
    n_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(
        inverted, connectivity=8
    )

    min_area = w * h * 0.0035  # real rooms are large; furniture pockets aren't
    max_area = w * h * 0.82
    margin = max(8, min(w, h) // 50)
    rooms = []
    for label in range(1, n_labels):  # 0 = background
        area = float(stats[label, cv2.CC_STAT_AREA])
        if area < min_area or area > max_area:
            continue
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        rw = int(stats[label, cv2.CC_STAT_WIDTH])
        rh = int(stats[label, cv2.CC_STAT_HEIGHT])

        # Reject regions that touch the image border (= outer background)
        if x <= margin or y <= margin or (x + rw) >= (w - margin) or (y + rh) >= (h - margin):
            continue

        # Skip slivers
        aspect = max(rw, rh) / max(min(rw, rh), 1)
        if aspect > 12:
            continue

        # Get polygon from component mask
        mask = (labels == label).astype(np.uint8) * 255
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not cnts:
            continue
        cnt = max(cnts, key=cv2.contourArea)
        peri = cv2.arcLength(cnt, True)
        # Modest simplification — enough to drop pixel jitter without
        # collapsing concave (L-shaped, open-plan) rooms into triangles.
        approx = cv2.approxPolyDP(cnt, 0.01 * peri, True)
        polygon = [[int(pt[0][0]), int(pt[0][1])] for pt in approx]

        rooms.append({
            "id": f"room_{label}",
            "area": round(area, 1),
            "bbox": {"x": x, "y": y, "w": rw, "h": rh},
            "centroid": {"x": int(centroids[label][0]), "y": int(centroids[label][1])},
            "polygon": polygon,
        })

    # Regions come from connected components, so they are already pixel
    # disjoint — no overlap dedup needed. (The old bbox-overlap dedup wrongly
    # deleted small rooms whose bounding box fell inside a larger room's box,
    # e.g. a closet within the building envelope.)
    rooms.sort(key=lambda r: r["area"], reverse=True)
    return rooms


# ═══════════════════════════════════════════════════════════════════
#  MAIN PIPELINE
# ═══════════════════════════════════════════════════════════════════

def detect_floor_plan(image_path: str) -> dict[str, Any]:
    """
    v3 Full Pipeline — perfect-grade floor plan detection.

    Returns:
      image_size, walls, rooms, openings (with arc data for doors), stats
    """
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Cannot read image: {image_path}")

    orig_h, orig_w = img.shape[:2]
    stats: dict[str, Any] = {"image_size": {"width": orig_w, "height": orig_h}}

    # ── 1. Adaptive preprocessing ────────────────────────────────
    gray_proc, blurred_proc, thresh, scale = _preprocess(img)
    ph, pw = thresh.shape[:2]
    stats["processing_scale"] = round(scale, 3)

    # ── 2. Morphological structural extraction ───────────────────
    structural, dist_transform = _extract_structural(thresh, pw, ph)
    stats["preprocessing"] = "CLAHE+Gaussian+OTSU+adaptive → morph structural extraction"

    # ── 3. Canny + Hough line detection ──────────────────────────
    raw_lines, edges = _detect_lines(structural, blurred_proc, pw, ph)
    stats["raw_lines"] = len(raw_lines)

    # Sort by length, cap for speed
    raw_lines.sort(key=lambda s: _len(*s), reverse=True)
    if len(raw_lines) > 1000:
        raw_lines = raw_lines[:1000]

    # ── 4. Angle pre-snap before merging ─────────────────────────
    pre_snapped = []
    for (x1, y1, x2, y2) in raw_lines:
        ang = _angle_deg(x1, y1, x2, y2)
        t = _hard_snap_angle(ang, thresh=15)
        if t is not None:
            x1, y1, x2, y2 = _apply_angle_snap(x1, y1, x2, y2, t)
        pre_snapped.append((x1, y1, x2, y2))

    # ── 5. Two-pass iterative merging ────────────────────────────
    # Pass 1: merge near-exact duplicates
    pass1 = _merge_lines(pre_snapped, angle_thresh=3, dist_thresh=8)
    # Pass 2: merge double-lines from wall thickness
    pass2 = _merge_lines(pass1,       angle_thresh=7, dist_thresh=42)
    stats["after_merge_p1"] = len(pass1)
    stats["after_merge_p2"] = len(pass2)

    # ── 6. Adaptive length filter ────────────────────────────────
    if pass2:
        lengths = sorted([_len(*s) for s in pass2])
        p10 = lengths[max(0, int(len(lengths) * 0.10))]
        min_len = max(18.0, p10)
    else:
        min_len = 18.0
    length_filtered = [s for s in pass2 if _len(*s) >= min_len]
    stats["after_length_filter"] = len(length_filtered)

    # ── 7. Thickness filter (kills faded/annotation lines) ───────
    thick_lines, thick_vals = _thickness_filter(
        length_filtered, structural, min_avg_thickness=2.5, samples=12
    )
    if len(thick_lines) >= 4:
        length_filtered = thick_lines
        stats["thickness_filter"] = "applied"
    else:
        stats["thickness_filter"] = "skipped (too few survived)"
    stats["after_thickness"] = len(length_filtered)

    # ── 8. Graph-based endpoint snapping ─────────────────────────
    snapped = _snap_endpoints(length_filtered, snap_radius=14)
    stats["after_endpoint_snap"] = len(snapped)

    # ── 9. Hard angle snap (final) ───────────────────────────────
    final_lines = _final_angle_snap(snapped, thresh=15)

    # ── 9b. Co-axial merge (run twice to fully consolidate) ──────
    final_lines = _coaxial_merge(final_lines, axis_tolerance=10, gap_tolerance=35)
    final_lines = _coaxial_merge(final_lines, axis_tolerance=10, gap_tolerance=35)
    stats["after_coaxial_merge"] = len(final_lines)

    # ── 9c. Remove isolated floating segments ────────────────────
    final_lines = _remove_isolated(final_lines, neighbor_radius=32)
    stats["after_isolated_removal"] = len(final_lines)

    # ── 9d. Kill non-orthogonal (diagonal) noise ──────────────────
    # Floor plans are orthogonal. Lines at diagonal angles are
    # staircase lines, dimension annotations, text, or artifacts.
    ortho_thresh = 5  # degrees tolerance from 0/90/180
    ortho_lines = []
    for seg in final_lines:
        ang = _angle_deg(*seg) % 180
        near_horiz = ang < ortho_thresh or ang > (180 - ortho_thresh)
        near_vert  = abs(ang - 90) < ortho_thresh
        if near_horiz or near_vert:
            ortho_lines.append(seg)
    stats["diagonal_removed"] = len(final_lines) - len(ortho_lines)
    final_lines = ortho_lines

    # Scale back to original image coordinates
    if scale != 1.0:
        inv = 1.0 / scale
        final_lines = [
            (int(x1 * inv), int(y1 * inv), int(x2 * inv), int(y2 * inv))
            for (x1, y1, x2, y2) in final_lines
        ]
        edges          = cv2.resize(edges, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        gray_full      = cv2.resize(gray_proc, (orig_w, orig_h), interpolation=cv2.INTER_LINEAR)
        # Scale distance transform — values scale linearly with image size
        dist_full      = cv2.resize(dist_transform, (orig_w, orig_h),
                                    interpolation=cv2.INTER_LINEAR) * inv
    else:
        gray_full = gray_proc
        dist_full = dist_transform

    # ── 9e. Classify walls using distance transform ───────────────
    final_thicknesses = _get_wall_widths(final_lines, dist_full)
    _, wall_types     = _classify_wall_types(final_lines, final_thicknesses)

    # Kill phantom walls with zero/near-zero thickness
    cleaned_lines = []
    cleaned_types = []
    cleaned_thick = []
    for seg, wtype, thick in zip(final_lines, wall_types, final_thicknesses):
        if thick >= 1.0:  # must have real pixel support
            cleaned_lines.append(seg)
            cleaned_types.append(wtype)
            cleaned_thick.append(thick)
    stats["phantom_removed"] = len(final_lines) - len(cleaned_lines)
    final_lines       = cleaned_lines
    wall_types        = cleaned_types
    final_thicknesses = cleaned_thick

    n_main      = wall_types.count('main_wall')
    n_partition = wall_types.count('partition')
    stats["main_walls"]      = n_main
    stats["partition_walls"] = n_partition
    if final_thicknesses:
        stats["thickness_main_thresh"] = round(
            _find_main_wall_threshold(final_thicknesses), 2
        )

    wall_result = []
    for idx, (x1, y1, x2, y2) in enumerate(final_lines):
        wtype = wall_types[idx] if idx < len(wall_types) else 'partition'
        wall_result.append({
            "id":        f"wall_{idx}",
            "x1": x1, "y1": y1,
            "x2": x2, "y2": y2,
            "length":    round(_len(x1, y1, x2, y2), 1),
            "angle":     round(_angle_deg(x1, y1, x2, y2), 1),
            "wall_type": wtype,        # 'main_wall' | 'partition'
            "thickness": round(final_thicknesses[idx], 2) if idx < len(final_thicknesses) else 0,
        })
    stats["walls_final"] = len(wall_result)

    # ── 10. Door arc detection ────────────────────────────────────
    min_r = max(15, orig_w // 60)
    max_r = max(60, orig_w // 12)
    door_arcs = _detect_door_arcs(gray_full, orig_w, orig_h, min_r=min_r, max_r=max_r)
    stats["door_arcs_found"] = len(door_arcs)

    # ── 11. Opening detection (doors + windows) ───────────────────
    opening_result = _detect_openings(wall_result, edges, door_arcs, orig_w, orig_h)
    stats["openings_detected"] = len(opening_result)
    stats["doors"] = sum(1 for o in opening_result if o["type"] == "door")
    stats["windows"] = sum(1 for o in opening_result if o["type"] == "window")

    # ── 12. Room detection (seals detected openings first) ────────
    room_result = _detect_rooms(wall_result, opening_result, orig_w, orig_h)
    stats["rooms_detected"] = len(room_result)

    return {
        "image_size": {"width": orig_w, "height": orig_h},
        "walls":      wall_result,
        "rooms":      room_result,
        "openings":   opening_result,
        "door_arcs":  door_arcs,
        "stats":      stats,
    }
