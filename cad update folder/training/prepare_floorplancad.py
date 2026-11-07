"""Turn the Voxel51/FloorPlanCAD copy on Hugging Face into a YOLO detection dataset.

This copy's class NAMES are wrong for doors and windows (checked by eye on contact
sheets of every class, Nov 2026); its boxes are fine. LABEL_MAP below uses what the
boxes really mark:

    name in the copy   what it marks     evidence
    double_door        single door       one leaf, one quarter arc
    sliding_door       double door       two leaves, two arcs
    window             sliding door      thin strip, door codes (PM...)
    stair              window            thin strip, window codes (ZC1805, C10524)

Images are normalised to dark lines on white, because the plans the model will read
are rendered that way from CAD (colour must not become a feature). Tiles from one
drawing (file name "<drawing>-<tile>.png") never appear in both train and val, so
validation scores aren't inflated by near-duplicates.

usage: python prepare_floorplancad.py --root <dataset folder> --out <yolo folder>
"""
import argparse
import json
import os
import random

import cv2
import numpy as np

LABEL_MAP = {"double_door": "door_single", "sliding_door": "door_double",
             "window": "door_sliding", "stair": "window"}
CLASSES = ["door_single", "door_double", "door_sliding", "window"]
VAL_SHARE = 0.10
SEED = 7


def clean_image(src, dst):
    """RGBA drawing -> dark lines on white; any coloured line becomes dark."""
    img = cv2.imread(src, cv2.IMREAD_UNCHANGED)
    if img is None:
        return False
    if img.ndim == 2:
        gray = img
    else:
        if img.shape[2] == 4:
            alpha = img[..., 3:] / 255.0
            img = (img[..., :3] * alpha + 255.0 * (1.0 - alpha)).astype(np.uint8)
        gray = img.min(axis=2)          # min, not luma: a yellow line must not fade out
    ink = np.clip((255.0 - gray) * 3.0, 0, 255)
    cv2.imwrite(dst, (255.0 - ink).astype(np.uint8), [cv2.IMWRITE_JPEG_QUALITY, 92])
    return True


def yolo_lines(detections):
    """FiftyOne boxes (top-left x, y, w, h, normalised) -> YOLO label lines (centre x, y, w, h)."""
    out = []
    for d in detections:
        name = LABEL_MAP.get(d["label"])
        if name is None:
            continue
        x, y, w, h = d["bounding_box"]
        x0, y0 = max(0.0, x), max(0.0, y)
        x1, y1 = min(1.0, x + w), min(1.0, y + h)
        if x1 - x0 < 0.002 or y1 - y0 < 0.002:
            continue
        out.append(f"{CLASSES.index(name)} {(x0 + x1) / 2:.6f} {(y0 + y1) / 2:.6f} {x1 - x0:.6f} {y1 - y0:.6f}")
    return out


def split_by_drawing(names):
    """{file name: "train"|"val"}, whole drawings at a time."""
    drawings = sorted({n.split("-")[0] for n in names})
    random.Random(SEED).shuffle(drawings)
    val = set(drawings[:max(1, round(len(drawings) * VAL_SHARE))])
    return {n: ("val" if n.split("-")[0] in val else "train") for n in names}


def prepare(root, out, images_dir="data"):
    with open(os.path.join(root, "samples.json"), encoding="utf-8") as f:
        samples = json.load(f)["samples"]
    present = []
    for s in samples:
        name = s["filepath"].split("/")[-1]
        if os.path.isfile(os.path.join(root, images_dir, name)):
            present.append((name, s))
    split = split_by_drawing([n for n, _ in present])
    for part in ("train", "val"):
        os.makedirs(os.path.join(out, "images", part), exist_ok=True)
        os.makedirs(os.path.join(out, "labels", part), exist_ok=True)
    stats = {"train": [0, 0], "val": [0, 0]}
    counts = dict.fromkeys(CLASSES, 0)
    for name, s in present:
        part = split[name]
        stem = os.path.splitext(name)[0]
        if not clean_image(os.path.join(root, images_dir, name), os.path.join(out, "images", part, stem + ".jpg")):
            continue
        lines = yolo_lines((s.get("ground_truth") or {}).get("detections", []))
        with open(os.path.join(out, "labels", part, stem + ".txt"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        stats[part][0] += 1
        stats[part][1] += len(lines)
        for line in lines:
            counts[CLASSES[int(line.split()[0])]] += 1
    with open(os.path.join(out, "data.yaml"), "w", encoding="utf-8") as f:
        f.write(f"path: {os.path.abspath(out)}\ntrain: images/train\nval: images/val\nnames:\n")
        for i, c in enumerate(CLASSES):
            f.write(f"  {i}: {c}\n")
    return {"images_boxes": stats, "classes": counts}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--images", default="data")
    a = ap.parse_args()
    print(prepare(a.root, a.out, a.images))
