"""CAD detection: one drawing of an inspected file -> walls, doors/windows, rooms.

Output is the same JSON schema as detector.detect_floor_plan / ml_detector
(pixel space, so the 2D editor and 3D scene work unchanged), plus exact
real-world measurements, and a preview PNG drawn in that exact pixel space to
serve as the editor's background image.
"""
import hashlib
import json
import math
import os
import pickle
import sys
import time

from .converter import CadError
from .layers import ROLES
from .loader import NAME_TO_M
from .openings import attach_indices, find_openings, is_door_name, is_window_name
from .pipeline import INSPECT_VERSION, inspect_file, session_dir
from .render import render_preview
from .rooms import find_rooms
from .walls import build_walls

TARGET_LONG_PX = 2000
MARGIN_M = 1.0


class PlanNotChosen(CadError):
    status = 422


def _load_state(src_path, cache_root):
    insp = inspect_file(src_path, cache_root)
    path = os.path.join(session_dir(cache_root, insp["session_id"]), "state.pkl")
    if os.path.isfile(path):
        with open(path, "rb") as f:
            state = pickle.load(f)
        if state.get("inspect_version") == INSPECT_VERSION:
            return insp, state
    insp = inspect_file(src_path, cache_root, use_cache=False)
    with open(path, "rb") as f:
        return insp, pickle.load(f)


def detect_file(src_path, cache_root, cluster_id=None, layer_roles=None, units_name=None):
    """`cluster_id`: which drawing (default: the suggested floor plan).
    `layer_roles`: {layer: role} overrides of the suggested roles.
    `units_name`: "mm"/"cm"/"m"/"in"/"ft" override of the detected units."""
    t_start = time.time()
    insp, state = _load_state(src_path, cache_root)
    clusters = {c["id"]: c for c in insp["clusters"]}
    if cluster_id is None:
        cluster_id = next((c["id"] for c in insp["clusters"] if c["suggested"]), None)
        if cluster_id is None:
            raise PlanNotChosen("No drawing in this file was confidently identified as a floor plan; "
                                "choose one in the review step.")
    if cluster_id not in clusters:
        raise PlanNotChosen(f"Unknown drawing '{cluster_id}'.")
    cluster = clusters[cluster_id]

    roles = {l["name"]: l["suggested_role"] for l in insp["layers"]}
    for name, role in (layer_roles or {}).items():
        if role not in ROLES:
            raise CadError(f"Unknown role '{role}' for layer '{name}'. Use one of: {', '.join(ROLES)}.")
        roles[name] = role
    if units_name:
        if units_name not in NAME_TO_M:
            raise CadError(f"Unknown unit '{units_name}'. Use one of: {', '.join(NAME_TO_M)}.")
        mpu = NAME_TO_M[units_name]
    else:
        mpu = insp["units"]["metres_per_unit"]

    records, inserts = state["records"], state["inserts"]
    members = state["members"][cluster_id]
    x0, y0, x1, y1 = cluster["bbox"]
    W_m, H_m = (x1 - x0) * mpu, (y1 - y0) * mpu

    def to_m(x, y):
        return ((x - x0) * mpu, (y - y0) * mpu)

    def seg_m(s):
        return (*to_m(s[0], s[1]), *to_m(s[2], s[3]))

    def arc_m(a):
        return (*to_m(a[0], a[1]), a[2] * mpu, a[3], *to_m(a[4], a[5]), *to_m(a[6], a[7]))

    # Door / window symbols (blocks). Their lines must not be read as walls.
    member_set = set(members)
    door_blocks, window_blocks, in_symbol = [], [], set()
    for ins in inserts:
        role = roles.get(ins.layer)
        kind = ("door" if is_door_name(ins.name) or role == "door"
                else "window" if is_window_name(ins.name) or role == "window" else None)
        if kind is None:
            continue
        idxs = [i for i in range(ins.start, ins.end) if i in member_set and i not in in_symbol]
        if not idxs:
            continue
        in_symbol.update(idxs)
        pts = [to_m(*p) for i in idxs for p in ((records[i].bbox[0], records[i].bbox[1]),
                                                   (records[i].bbox[2], records[i].bbox[3]))]
        arcs = [arc_m(records[i].arc) for i in idxs if records[i].arc]
        (door_blocks if kind == "door" else window_blocks).append({"arcs": arcs, "points": pts})

    wall_segs, wall_arcs, window_segs, loose_arcs, texts = [], [], [], [], []
    for i in members:
        r = records[i]
        if r.text:
            texts.append((*to_m(*r.center), r.text))
        if i in in_symbol:
            continue
        role = roles.get(r.layer, "ignore")
        if r.arc:
            loose_arcs.append(arc_m(r.arc))  # openings.py checks it really swings from a wall
        if not r.segs:
            continue
        if role == "wall":
            if r.kind == "ARC":
                wall_arcs.append(arc_m(r.arc))
            else:
                wall_segs.extend(seg_m(s) for s in r.segs)
        elif role == "window":
            window_segs.extend(seg_m(s) for s in r.segs)

    walls, wall_info = build_walls(wall_segs, wall_arcs)
    walls, openings = find_openings(walls, loose_arcs, door_blocks, window_blocks, window_segs)
    openings = attach_indices(walls, openings)
    rooms = find_rooms(walls, texts, W_m, H_m)

    ppm = TARGET_LONG_PX / (max(W_m, H_m) + 2 * MARGIN_M)
    img_w = int(math.ceil((W_m + 2 * MARGIN_M) * ppm))
    img_h = int(math.ceil((H_m + 2 * MARGIN_M) * ppm))

    def px(x, y):
        return (int(round((x + MARGIN_M) * ppm)), int(round((H_m + MARGIN_M - y) * ppm)))

    preview_name = _preview_name(cluster_id, roles, mpu)
    preview_path = os.path.join(session_dir(cache_root, insp["session_id"]), preview_name)
    if not os.path.isfile(preview_path):
        render_preview(records, members, roles, preview_path, img_w, img_h,
                       x0, y1, ppm * mpu, MARGIN_M * ppm, MARGIN_M * ppm)

    result = _to_schema(walls, openings, rooms, px, ppm, img_w, img_h)
    ft_per_px = 1.0 / (ppm * 0.3048)
    result["stats"] = {
        "engine": "cad_vector",
        "method": wall_info["mode"],
        "cluster_id": cluster_id,
        "image_size": {"width": img_w, "height": img_h},
        "walls_final": len(result["walls"]),
        "rooms_detected": len(result["rooms"]),
        "openings_detected": len(result["openings"]),
        "doors": sum(1 for o in result["openings"] if o["type"] == "door"),
        "windows": sum(1 for o in result["openings"] if o["type"] == "window"),
        "wall_pairing": wall_info,
        "units": {"name": units_name or insp["units"]["name"], "metres_per_unit": mpu},
        "scale_ft_per_px": round(ft_per_px, 6),
        "label_dim_check": _label_check(result["rooms"]),
        "seconds": round(time.time() - t_start, 2),
    }
    result["measurements"] = {
        "scale_ft_per_px": round(ft_per_px, 6),
        "building_ft": [round(W_m / 0.3048, 1), round(H_m / 0.3048, 1)],
        "dimension_labels_read": [r["label"] for r in result["rooms"] if r.get("label")],
    }
    result["source"] = "cad"
    result["session_id"] = insp["session_id"]
    result["preview_file"] = preview_name
    return result


def _preview_name(cluster_id, roles, mpu):
    key = json.dumps([sorted(roles.items()), mpu]).encode()
    return f"preview_{cluster_id}_{hashlib.sha1(key).hexdigest()[:10]}.png"


def _to_schema(walls, openings, rooms, px, ppm, img_w, img_h):
    backend = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", "backend")
    if backend not in sys.path:
        sys.path.insert(0, backend)
    from detector import _angle_deg, _classify_wall_types, _len

    lines = [(*px(w[0], w[1]), *px(w[2], w[3])) for w in walls]
    thick = [max(1.0, w[4] * ppm) for w in walls]
    _, wall_types = _classify_wall_types(lines, thick) if lines else ([], [])
    out_walls = []
    for i, (l, w) in enumerate(zip(lines, walls)):
        out_walls.append({
            "id": f"wall_{i}",
            "x1": l[0], "y1": l[1], "x2": l[2], "y2": l[3],
            "length": round(_len(*l), 1),
            "angle": round(_angle_deg(*l), 1),
            "wall_type": wall_types[i] if i < len(wall_types) else "partition",
            "thickness": round(thick[i], 2),
            "thickness_m": round(w[4], 3),
            "length_ft": round(math.hypot(w[2] - w[0], w[3] - w[1]) / 0.3048, 2),
        })
    out_openings = []
    for i, o in enumerate(openings):
        x, y = px(o["x"], o["y"])
        out_openings.append({
            "id": f"opening_{i}",
            "wall_id": f"wall_{o['wall_index']}",
            "x": x, "y": y,
            "width_px": round(o["width"] * ppm, 1),
            "width_m": round(o["width"], 3),
            "type": o["type"],
        })
    out_rooms = []
    for i, r in enumerate(rooms):
        bx, by, bw, bh = r["bbox_m"]
        tl = px(bx, by + bh)
        cx, cy = px(*r["centroid_m"])
        room = {
            "id": f"room_{i}",
            "type": r["type"],
            "label": r["label"],
            "area": round(r["area_m2"] * ppm * ppm, 1),
            "bbox": {"x": tl[0], "y": tl[1], "w": int(round(bw * ppm)), "h": int(round(bh * ppm))},
            "centroid": {"x": cx, "y": cy},
            "polygon": [list(px(*p)) for p in r["polygon_m"]],
            "computed_dim_ft": [round(bw / 0.3048, 1), round(bh / 0.3048, 1)],
            "area_sqft": round(r["area_m2"] * 10.7639, 1),
        }
        if r["label_dim_ft"]:
            room["label_dim"] = r["label"]
            room["label_dim_ft"] = r["label_dim_ft"]
        out_rooms.append(room)
    return {"image_size": {"width": img_w, "height": img_h}, "walls": out_walls,
            "rooms": out_rooms, "openings": out_openings, "door_arcs": []}


def _label_check(rooms):
    """Compare each labelled room size (e.g. 12'-3" x 14'-0") with the size measured from the walls."""
    errors = []
    for r in rooms:
        if r.get("label_dim_ft"):
            lab = sorted(r["label_dim_ft"])
            got = sorted(r["computed_dim_ft"])
            errors.append(max(abs(g - l) / l for g, l in zip(got, lab) if l > 0) * 100.0)
    if not errors:
        return {"rooms_checked": 0}
    errors.sort()
    return {"rooms_checked": len(errors), "median_error_pct": round(errors[len(errors) // 2], 1),
            "max_error_pct": round(errors[-1], 1)}
