"""Draft a ground-truth label file for one plan, plus a numbered review image.

usage: python draft_labels.py <slug> <file in repo root | archive.zip::member> <cluster id> [units]

The draft is the current vector detection (walls, doors, windows) plus every
room name printed in the drawing, and a list of door-swing arcs no detected
door accounts for ("check"). It is NOT ground truth until a person has checked
the review image and corrected the file; then set "status": "reviewed".
"""
import json
import math
import os
import pickle
import sys

import cv2
import numpy as np

from bench_core import LABELS, OUT, Plan, source_path, CACHE  # noqa: F401
from cad.pipeline import inspect_file, session_dir
from cad.rooms import parse_label_dims_ft
from cad.vocab import room_type_for


def door_arcs(records, members, mpu):
    out = []
    for i in members:
        a = records[i].arc
        if a and 80.0 <= a[3] <= 100.0 and 0.5 <= a[2] * mpu <= 1.3:
            out.append(a)
    return out


def main():
    slug, fname, cid = sys.argv[1:4]
    units = sys.argv[4] if len(sys.argv) > 4 else None
    src = source_path(fname)
    insp = inspect_file(src, CACHE)
    cluster = next(c for c in insp["clusters"] if c["id"] == cid)
    label = {"plan": slug, "file": fname, "plan_bbox": cluster["bbox"], "units": units,
             "status": "draft", "notes": [], "walls": [], "doors": [], "windows": [], "rooms": [], "check": []}
    plan = Plan(label)
    pred = plan.normalise(plan.detect_vector())
    label["walls"] = [{"id": f"w{i}", "a": [round(w[0], 3), round(w[1], 3)], "b": [round(w[2], 3), round(w[3], 3)],
                       "t": round(w[4], 3)} for i, w in enumerate(pred["walls"])]
    for key, prefix in (("doors", "d"), ("windows", "win")):
        label[key] = [{"id": f"{prefix}{i}", "at": [round(o[0], 3), round(o[1], 3)], "w": round(o[2], 3)}
                      for i, o in enumerate(pred[key])]

    with open(os.path.join(session_dir(CACHE, insp["session_id"]), "state.pkl"), "rb") as f:
        state = pickle.load(f)
    records, members = state["records"], state["members"][cid]
    x0, y0 = label["plan_bbox"][:2]
    mpu = plan.mpu
    for i in members:
        r = records[i]
        if r.text and room_type_for(r.text):
            cx, cy = r.center
            label["rooms"].append({"id": f"r{len(label['rooms'])}", "name": r.text.replace("\n", " ").strip(),
                                   "type": room_type_for(r.text),
                                   "at": [round((cx - x0) * mpu, 3), round((cy - y0) * mpu, 3)],
                                   "dims_ft": parse_label_dims_ft(r.text)})
    for a in door_arcs(records, members, mpu):
        hx, hy = (a[0] - x0) * mpu, (a[1] - y0) * mpu
        if all(math.hypot(hx - d["at"][0], hy - d["at"][1]) > 1.5 for d in label["doors"]):
            label["check"].append({"id": f"a{len(label['check'])}", "hinge": [round(hx, 3), round(hy, 3)],
                                   "r": round(a[2] * mpu, 3)})

    os.makedirs(LABELS, exist_ok=True)
    path = os.path.join(LABELS, f"{slug}.json")
    if os.path.exists(path):
        path = os.path.join(LABELS, f"{slug}.draft.json")   # never overwrite a reviewed file
    with open(path, "w", encoding="utf-8") as f:
        json.dump(label, f, indent=1, ensure_ascii=False)
    review_image(plan, label, os.path.join(OUT, f"{slug}_review.png"))
    print(path, {k: len(label[k]) for k in ("walls", "doors", "windows", "rooms", "check")})


def review_image(plan, label, out_path):
    det_preview = next(f for f in os.listdir(plan.sdir) if f.startswith(f"preview_{plan.cluster['id']}_"))
    img = cv2.imread(os.path.join(plan.sdir, det_preview))
    h, w = img.shape[:2]
    # 1 m grid with metre numbers along the top and left edges
    for gx in range(-1, int(plan.W_m) + 2):
        px, _ = plan.m_to_px(gx, 0)
        cv2.line(img, (px, 0), (px, h), (60, 60, 60), 1)
        cv2.putText(img, str(gx), (px + 2, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 160), 1)
    for gy in range(-1, int(plan.H_m) + 2):
        _, py = plan.m_to_px(0, gy)
        cv2.line(img, (0, py), (w, py), (60, 60, 60), 1)
        cv2.putText(img, str(gy), (2, py - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (160, 160, 160), 1)
    font = cv2.FONT_HERSHEY_SIMPLEX
    for wl in label["walls"]:
        a, b = plan.m_to_px(*wl["a"]), plan.m_to_px(*wl["b"])
        cv2.line(img, a, b, (255, 255, 0), 2)
        cv2.putText(img, wl["id"], ((a[0] + b[0]) // 2 + 3, (a[1] + b[1]) // 2 - 3), font, 0.45, (255, 255, 0), 1)
    for key, col in (("doors", (0, 140, 255)), ("windows", (255, 120, 0))):
        for o in label[key]:
            c = plan.m_to_px(*o["at"])
            cv2.circle(img, c, max(6, int(o["w"] * plan.ppm / 2)), col, 2)
            cv2.putText(img, o["id"], (c[0] + 6, c[1] + 16), font, 0.55, col, 2)
    for r in label["rooms"]:
        c = plan.m_to_px(*r["at"])
        cv2.circle(img, c, 6, (0, 220, 0), -1)
        cv2.putText(img, r["id"], (c[0] + 8, c[1] - 8), font, 0.6, (0, 220, 0), 2)
    for a in label["check"]:
        c = plan.m_to_px(*a["hinge"])
        cv2.drawMarker(img, c, (0, 0, 255), cv2.MARKER_TILTED_CROSS, 22, 3)
        cv2.putText(img, a["id"], (c[0] + 8, c[1] + 8), font, 0.6, (0, 0, 255), 2)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    cv2.imwrite(out_path, img)


if __name__ == "__main__":
    main()
