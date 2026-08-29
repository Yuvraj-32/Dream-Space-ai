"""
eval_detect.py — batch detection harness for iterating on detector quality.

Runs one or both engines over a set of floor-plan images, writes an annotated
overlay PNG + the raw JSON per image, and prints a comparison table. Unlike
tests/test_regression.py (which guards against regressions on two fixtures),
this is the exploratory tool: point it at every plan in the repo, look at the
overlays, fix what's wrong, re-run, diff the table.

Usage (from backend/):
    venv\\Scripts\\python eval_detect.py                     # all plans, ml engine
    venv\\Scripts\\python eval_detect.py --engine both
    venv\\Scripts\\python eval_detect.py --measure           # + OCR dimensions
    venv\\Scripts\\python eval_detect.py --images 3br,truoba # substring filter

Output lands in backend/eval_out/<engine>/ (git-ignored).
"""
import argparse
import glob
import json
import math
import os
import sys
import time
import traceback

import cv2
import numpy as np

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BACKEND_DIR)
OUT_DIR = os.path.join(BACKEND_DIR, "eval_out")
sys.path.insert(0, BACKEND_DIR)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff")
# Max overlay size on disk — keeps them reviewable without downscaling detail
# away on big CAD scans.
MAX_OUT_DIM = 1600

# BGR
C_MAIN = (60, 60, 255)      # red      — main/structural wall
C_PART = (80, 220, 80)      # green    — partition wall
C_DOOR = (255, 130, 0)      # blue     — door
C_WIN = (255, 220, 0)       # cyan     — window
C_ROOM = (255, 0, 200)      # magenta  — room polygon


def discover_images(filters=None):
    """Every floor-plan image in the repo root + tests/fixtures."""
    paths = []
    for ext in IMAGE_EXTS:
        paths += glob.glob(os.path.join(ROOT_DIR, f"*{ext}"))
        paths += glob.glob(os.path.join(BACKEND_DIR, "tests", "fixtures", f"*{ext}"))
    paths = sorted(set(paths))
    if filters:
        paths = [p for p in paths
                 if any(f.lower() in os.path.basename(p).lower() for f in filters)]
    return paths


def short_name(path):
    """Stable, filesystem-safe short label. Keeps the extension so same-named
    variants of one plan (foo.jpg vs foo.webp) don't overwrite each other."""
    base, ext = os.path.splitext(os.path.basename(path))
    base = "".join(c if c.isalnum() or c in "-_" else "_" for c in base)
    return f"{base[:44]}_{ext.lstrip('.')}"


def draw_overlay(img, result):
    """Annotated copy of the plan: walls, rooms, openings.

    Draw order and orientation matter for judging quality:
      - openings are drawn ALONG their host wall's direction (a 1.2m window on
        a vertical wall is a tall thin bar, not a wide box), otherwise every
        opening looks oversized and spilling outside the building;
      - rooms are drawn last and inset, so their outlines don't hide beneath
        the thicker wall strokes they share edges with.
    """
    scale = max(img.shape[:2]) / 1200.0     # stroke weights that survive resize
    t = max(1, int(round(scale)))
    # Fade the plan so the annotations read clearly on top of black CAD lines.
    over = cv2.addWeighted(img, 0.45, np.full_like(img, 255), 0.55, 0)

    walls_by_id = {w["id"]: w for w in result.get("walls", [])}

    for w in result.get("walls", []):
        main = w.get("wall_type") == "main_wall"
        cv2.line(over, (w["x1"], w["y1"]), (w["x2"], w["y2"]),
                 C_MAIN if main else C_PART, (4 if main else 2) * t, cv2.LINE_AA)
        # Endpoints — gaps between walls are the main geometry failure mode,
        # so make every endpoint visible.
        for px, py in ((w["x1"], w["y1"]), (w["x2"], w["y2"])):
            cv2.circle(over, (px, py), 3 * t, (0, 0, 0), -1, cv2.LINE_AA)

    for o in result.get("openings", []):
        cx, cy = int(o["x"]), int(o["y"])
        half = max(6, float(o.get("width_px", 40)) / 2)
        w = walls_by_id.get(o.get("wall_id"))
        # Unit vector along the host wall; default horizontal if unknown.
        ux, uy = 1.0, 0.0
        if w:
            dx, dy = w["x2"] - w["x1"], w["y2"] - w["y1"]
            n = math.hypot(dx, dy)
            if n > 1e-6:
                ux, uy = dx / n, dy / n
        depth = max(3, 5 * t)               # perpendicular half-thickness
        px, py = -uy * depth, ux * depth
        quad = np.array([
            [cx - ux * half + px, cy - uy * half + py],
            [cx + ux * half + px, cy + uy * half + py],
            [cx + ux * half - px, cy + uy * half - py],
            [cx - ux * half - px, cy - uy * half - py],
        ], dtype=np.int32)
        color = C_DOOR if o["type"] == "door" else C_WIN
        cv2.polylines(over, [quad], True, color, 2 * t, cv2.LINE_AA)
        if o["type"] == "door":
            cv2.circle(over, (cx, cy), 4 * t, color, -1, cv2.LINE_AA)

    # Rooms last, inset toward their centroid so shared edges stay visible.
    for rm in result.get("rooms", []):
        poly = np.array(rm.get("polygon", []), dtype=np.int32)
        if len(poly) >= 3:
            c = poly.mean(axis=0)
            inset = (poly - c) * 0.985 + c
            cv2.polylines(over, [inset.astype(np.int32)], True, C_ROOM,
                          2 * t, cv2.LINE_AA)
        b = rm["bbox"]
        label = rm.get("type", "room")
        if rm.get("area_sqft"):
            label += f" {rm['area_sqft']:.0f}sf"
        cv2.putText(over, label, (b["x"] + 6, b["y"] + 26 * t),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6 * t, C_ROOM, 2 * t, cv2.LINE_AA)
    return over


def summarize(result, elapsed):
    walls = result.get("walls", [])
    rooms = result.get("rooms", [])
    ops = result.get("openings", [])
    stats = result.get("stats", {})
    return {
        "seconds": round(elapsed, 2),
        "walls": len(walls),
        "main_walls": sum(1 for w in walls if w.get("wall_type") == "main_wall"),
        "rooms": len(rooms),
        "doors": sum(1 for o in ops if o["type"] == "door"),
        "windows": sum(1 for o in ops if o["type"] == "window"),
        "room_types": sorted({r.get("type", "?") for r in rooms}),
        "method": stats.get("method"),
        "scale_ft_per_px": stats.get("scale_ft_per_px"),
        "ml_fallback": stats.get("ml_fallback"),
        "measure_error": stats.get("measure_error"),
    }


def run_one(path, engine, measure):
    from main import run_detection
    t0 = time.perf_counter()
    result = run_detection(path, engine, measure)
    return result, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", default="ml", choices=["classical", "ml", "auto", "both"])
    ap.add_argument("--measure", action="store_true", help="run OCR measurement pass")
    ap.add_argument("--images", default=None, help="comma-separated name filters")
    ap.add_argument("--tag", default=None, help="output subdir suffix (for A/B runs)")
    ap.add_argument("--redraw", action="store_true",
                    help="re-render overlays from saved JSON (no inference)")
    args = ap.parse_args()

    filters = [f.strip() for f in args.images.split(",")] if args.images else None
    images = discover_images(filters)
    if not images:
        print("No images found.")
        return 1

    engines = ["classical", "ml"] if args.engine == "both" else [args.engine]
    print(f"{len(images)} image(s) × {len(engines)} engine(s)\n")

    summary = {}
    for engine in engines:
        out_dir = os.path.join(OUT_DIR, engine + (f"-{args.tag}" if args.tag else ""))
        os.makedirs(out_dir, exist_ok=True)
        summary[engine] = {}

        for path in images:
            name = short_name(path)
            img = cv2.imread(path)
            if img is None:
                print(f"  !! unreadable: {path}")
                continue
            json_path = os.path.join(out_dir, f"{name}.json")
            if args.redraw:
                if not os.path.exists(json_path):
                    continue
                with open(json_path) as f:
                    result = json.load(f)
                elapsed = 0.0
            else:
                try:
                    result, elapsed = run_one(path, engine, args.measure)
                except Exception:
                    print(f"  !! {name} [{engine}] FAILED")
                    traceback.print_exc()
                    summary[engine][name] = {"error": True}
                    continue

            over = draw_overlay(img, result)
            h, w = over.shape[:2]
            if max(h, w) > MAX_OUT_DIM:
                s = MAX_OUT_DIM / max(h, w)
                over = cv2.resize(over, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
            cv2.imwrite(os.path.join(out_dir, f"{name}.png"), over)
            if not args.redraw:
                with open(json_path, "w") as f:
                    json.dump(result, f, indent=2)

            s = summarize(result, elapsed)
            summary[engine][name] = s
            note = s["ml_fallback"] or s["measure_error"] or s["method"] or ""
            print(f"  {name[:40]:42s} [{engine:9s}] "
                  f"walls={s['walls']:3d} rooms={s['rooms']:2d} "
                  f"doors={s['doors']:2d} wins={s['windows']:2d} "
                  f"{s['seconds']:5.1f}s  {str(note)[:40]}")

    with open(os.path.join(OUT_DIR, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nOverlays + JSON → {OUT_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
