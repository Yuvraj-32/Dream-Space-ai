"""Rooms: enclosed spaces between the walls, named from the drawing's own labels. Metres, Y up.

Walls are painted at their real thickness onto a 2 cm raster, small gaps are
closed, and every enclosed empty region that doesn't touch the outside is a
room — so room areas are net (inside the walls), which is also what plan labels
like "BED ROOM - 3 12'-3\"X14'-0\"" state. That makes the labels a free accuracy
check: `label_dim_ft` vs the geometry's `computed_dim_ft`.
"""
import math
import os
import re
import sys

import cv2
import numpy as np

from .vocab import room_type_for

RES = 50                 # px per metre (2 cm)
CLOSE_M = 0.20           # close wall gaps up to this (not doorways)
MIN_ROOM_M2 = 1.0
MARGIN_M = 1.0

_METRIC_RE = re.compile(r"(\d+(?:\.\d+)?)\s*[xX×]\s*(\d+(?:\.\d+)?)")


def _parse_feet_pair(text):
    backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from measurements import _parse_dim_token  # reuse the image pipeline's feet-inches parser
    vals = _parse_dim_token(text)
    return vals if len(vals) == 2 else None


def parse_label_dims_ft(text):
    """'BED ROOM - 3 12'-3\"X14'-0\"' -> [12.25, 14.0]; '3600 X 3000' -> [11.81, 9.84]."""
    if "'" in text:
        return _parse_feet_pair(text)
    m = _METRIC_RE.search(text)
    if not m:
        return None
    a, b = float(m.group(1)), float(m.group(2))
    scale = 0.001 if min(a, b) >= 100 else (1.0 if max(a, b) <= 30 else None)  # mm or m
    if scale is None:
        return None
    return [round(a * scale / 0.3048, 2), round(b * scale / 0.3048, 2)]


SEAL_COLLINEAR_M = (0.2, 2.0)   # doorway / window gap between two wall ends on one line
SEAL_RAY_M = (0.2, 1.6)         # door at a wall end, closing onto a perpendicular wall


def _unit(w):
    dx, dy = w[2] - w[0], w[3] - w[1]
    L = math.hypot(dx, dy)
    return L, dx / L, dy / L


def seal_gaps(walls):
    """Virtual lines across doorways/window gaps, used only to split rooms (never
    output as walls). Without them every unbridged doorway connects a room to
    the outside and the room is lost."""
    seals = []
    info = [_unit(w) for w in walls]
    for i, w in enumerate(walls):
        L, ux, uy = info[i]
        for end, (px, py), (dx, dy) in ((0, (w[0], w[1]), (-ux, -uy)), (1, (w[2], w[3]), (ux, uy))):
            best = None
            for j, v in enumerate(walls):
                if j == i:
                    continue
                Lv, vx, vy = info[j]
                parallel = abs(dx * vy - dy * vx) < math.sin(math.radians(3.0))
                if parallel:
                    off = abs((v[0] - px) * -dy + (v[1] - py) * dx)
                    if off > (w[4] + v[4]) / 2.0 + 0.05:
                        continue
                    t1 = (v[0] - px) * dx + (v[1] - py) * dy
                    t2 = (v[2] - px) * dx + (v[3] - py) * dy
                    near = min(t1, t2)
                    if SEAL_COLLINEAR_M[0] <= near <= SEAL_COLLINEAR_M[1]:
                        q = (v[0], v[1]) if t1 <= t2 else (v[2], v[3])
                        if best is None or near < best[0]:
                            best = (near, q)
                    continue
                if abs(dx * vy - dy * vx) < math.sin(math.radians(20.0)):
                    continue
                denom = dx * vy - dy * vx
                s = ((v[0] - px) * vy - (v[1] - py) * vx) / denom
                u = ((v[0] - px) * dy - (v[1] - py) * dx) / denom
                if SEAL_RAY_M[0] <= s <= SEAL_RAY_M[1] and -v[4] / 2.0 <= u <= Lv + v[4] / 2.0:
                    if best is None or s < best[0]:
                        best = (s, (px + dx * s, py + dy * s))
            if best is not None:
                seals.append((px, py, best[1][0], best[1][1]))
    return seals


def find_rooms(walls, texts, width_m, height_m):
    """walls: [(x1,y1,x2,y2,t)] m; texts: [(x, y, text)] m.
    Returns rooms with polygons in metres."""
    W = int(math.ceil((width_m + 2 * MARGIN_M) * RES))
    H = int(math.ceil((height_m + 2 * MARGIN_M) * RES))
    to_px = lambda x, y: (int(round((x + MARGIN_M) * RES)), int(round((height_m + MARGIN_M - y) * RES)))
    to_m = lambda px, py: (px / RES - MARGIN_M, height_m + MARGIN_M - py / RES)

    canvas = np.zeros((H, W), np.uint8)
    for x1, y1, x2, y2, t in walls:
        cv2.line(canvas, to_px(x1, y1), to_px(x2, y2), 255, max(2, int(round(t * RES))))
    for x1, y1, x2, y2 in seal_gaps(walls):
        cv2.line(canvas, to_px(x1, y1), to_px(x2, y2), 255, 3)
    k = max(3, int(round(CLOSE_M * RES)) | 1)
    closed = cv2.morphologyEx(canvas, cv2.MORPH_CLOSE, cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))

    n, labels, stats, cents = cv2.connectedComponentsWithStats(cv2.bitwise_not(closed), connectivity=4)
    rooms = []
    for lb in range(1, n):
        x, y, w, h, area = (int(v) for v in stats[lb])  # plain ints: results go to JSON
        if x == 0 or y == 0 or x + w >= W or y + h >= H:
            continue  # touches the canvas edge: that's outside the building
        area_m2 = area / (RES * RES)
        if area_m2 < MIN_ROOM_M2:
            continue
        mask = (labels == lb).astype(np.uint8)
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnt = max(cnts, key=cv2.contourArea)
        approx = cv2.approxPolyDP(cnt, 0.03 * RES, True)
        if len(approx) < 3:
            continue
        cx_m, cy_m = to_m(float(cents[lb][0]), float(cents[lb][1]))
        named = []
        for tx, ty, text in texts:
            px, py = to_px(tx, ty)
            if 0 <= px < W and 0 <= py < H and labels[py, px] == lb and room_type_for(text):
                has_dims = parse_label_dims_ft(text) is not None
                named.append((not has_dims, math.hypot(tx - cx_m, ty - cy_m), text))
        # A bedroom may also contain "DRESSER"/"WARDROBE" labels: prefer the name
        # that carries the room's size, then the one nearest the room's centre.
        label = min(named)[2] if named else None
        rooms.append({
            "polygon_m": [to_m(int(p[0][0]), int(p[0][1])) for p in approx],
            "area_m2": round(area_m2, 2),
            "bbox_m": (x / RES - MARGIN_M, height_m + MARGIN_M - (y + h) / RES, w / RES, h / RES),
            "centroid_m": (cx_m, cy_m),
            "type": room_type_for(label) if label else "undefined",
            "label": label,
            "label_dim_ft": parse_label_dims_ft(label) if label else None,
        })
    rooms.sort(key=lambda r: r["area_m2"], reverse=True)
    return rooms
