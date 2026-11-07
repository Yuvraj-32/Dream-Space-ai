"""Train the DreamSpace door/window detector on a Mac. See PLAN.md. Run it through run_mac.sh.

  trial    download + convert the dataset, check its labels, run a short training trial, and test
           that this Mac's GPU gives correct results. Prints a time estimate and PASS or FAIL.
  train    the full training run (needs a PASS). Run it again after any stop: it resumes.
  finish   final scores on the CPU, and package results_to_send/ (train runs this at the end).
  status   how far training has got.
"""
import argparse
import csv
import json
import math
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

WORK = os.path.join(HERE, "work")
DATASET = os.path.join(WORK, "dataset")
YOLO_DIR = os.path.join(WORK, "yolo")
TRIAL_DIR = os.path.join(WORK, "trial")
PROJECT = os.path.join(WORK, "runs")
SEND = os.path.join(HERE, "results_to_send")
TRIAL_RESULT = os.path.join(WORK, "trial_result.json")

REPO = "Voxel51/FloorPlanCAD"
REVISION = "b48e3b1932f987d053ab887f113b0a62959e943d"   # pinned: the class fix was checked on this version
FULL_COUNTS = {"door_single": 7808, "door_double": 4261, "door_sliding": 1910, "window": 6026}
IMGSZ = 800                        # DreamSpace reads plans at this size: do not change
EPOCHS = 60
TRIAL_FRACTION = 0.05
TRIAL_EPOCHS = 3


def default_batch():
    """Batch size by unified memory: too high makes macOS swap and crawl."""
    try:
        gb = os.sysconf("SC_PAGE_SIZE") * os.sysconf("SC_PHYS_PAGES") / 1024 ** 3
    except (AttributeError, ValueError, OSError):
        return 4
    return 4 if gb <= 10 else 8 if gb <= 18 else 12 if gb <= 26 else 16


# ── data ──────────────────────────────────────────────────────────────────
def download(limit=None):
    from huggingface_hub import hf_hub_download, snapshot_download
    if limit is None:
        snapshot_download(repo_id=REPO, repo_type="dataset", revision=REVISION, local_dir=DATASET,
                          allow_patterns=["samples.json", "data/*"])
    else:                          # a small sample, for testing this kit itself
        hf_hub_download(repo_id=REPO, repo_type="dataset", revision=REVISION, local_dir=DATASET,
                        filename="samples.json")
        with open(os.path.join(DATASET, "samples.json"), encoding="utf-8") as f:
            names = sorted(s["filepath"] for s in json.load(f)["samples"])
        for name in names[:limit]:
            hf_hub_download(repo_id=REPO, repo_type="dataset", revision=REVISION, local_dir=DATASET,
                            filename=name)
    print("Images downloaded:", len(os.listdir(os.path.join(DATASET, "data"))))


def convert(limit=None):
    from prepare_floorplancad import prepare
    shutil.rmtree(YOLO_DIR, ignore_errors=True)
    stats = prepare(DATASET, YOLO_DIR)
    print("Converted:", stats)
    if limit is None:              # the class fix only holds for the labelled counts we checked
        for name, expected in FULL_COUNTS.items():
            got = stats["classes"][name]
            if abs(got - expected) > 0.02 * expected:
                sys.exit(f"STOP: expected about {expected} '{name}' boxes, got {got}. "
                         "The dataset is not the one this kit was checked against.")
    return stats


def label_check_image(n=6):
    """Draw converted labels on a few images, for a person to look at."""
    import glob

    import cv2
    import numpy as np
    from prepare_floorplancad import CLASSES
    colours = [(0, 0, 255), (255, 0, 255), (0, 160, 0), (255, 120, 0)]
    labelled = [p for p in sorted(glob.glob(os.path.join(YOLO_DIR, "labels", "train", "*.txt")))
                if os.path.getsize(p) > 60]
    tiles = []
    for path in labelled[:: max(1, len(labelled) // n)][:n]:
        img = cv2.imread(path.replace(os.sep + "labels" + os.sep, os.sep + "images" + os.sep)[:-4] + ".jpg")
        h, w = img.shape[:2]
        with open(path, encoding="utf-8") as f:
            for line in f:
                c, x, y, bw, bh = line.split()
                c = int(c)
                x, y, bw, bh = float(x), float(y), float(bw), float(bh)
                p0 = (int((x - bw / 2) * w), int((y - bh / 2) * h))
                p1 = (int((x + bw / 2) * w), int((y + bh / 2) * h))
                cv2.rectangle(img, p0, p1, colours[c], 3)
                cv2.putText(img, CLASSES[c], (p0[0], max(16, p0[1] - 5)), 0, 0.6, colours[c], 2, cv2.LINE_AA)
        tiles.append(cv2.resize(img, (620, 620)))
    while len(tiles) % 3:
        tiles.append(np.full_like(tiles[0], 255))
    rows = [np.hstack(tiles[i:i + 3]) for i in range(0, len(tiles), 3)]
    out = os.path.join(HERE, "label_check.jpg")
    cv2.imwrite(out, np.vstack(rows))
    return out


# ── is this GPU telling the truth? ────────────────────────────────────────
def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


def boxes_agree(reference, other, min_iou=0.9, min_share=0.8):
    """Do two detectors' boxes land in the same places? (Reported Apple GPU faults corrupt
    box coordinates with no error.) Boxes are (x0, y0, x1, y1)."""
    if not reference:
        return None                # nothing to compare
    hits = sum(1 for r in reference if any(_iou(r, o) >= min_iou for o in other))
    return hits / len(reference) >= min_share


def losses_healthy(rows):
    """Reported Apple GPU faults show box/dfl loss stuck at 0, or NaN. Returns a problem or None."""
    for row in rows:
        for key in ("train/box_loss", "train/cls_loss", "train/dfl_loss"):
            value = float(row[key])
            if not math.isfinite(value) or value <= 0.0:
                return f"{key} = {value} in epoch {row.get('epoch')}"
    return None


def _read_results(path):
    with open(path, encoding="utf-8") as f:
        return [{k.strip(): v for k, v in row.items()} for row in csv.DictReader(f)]


def gpu_vs_cpu(weights, device, images):
    """Same model, same images, on this device and on the CPU."""
    from ultralytics import YOLO
    model = YOLO(weights)
    verdicts = []
    for img in images:
        boxes = {}
        for d in (device, "cpu"):
            r = model.predict(img, imgsz=IMGSZ, conf=0.01, max_det=20, device=d, verbose=False)[0]
            boxes[d] = [tuple(float(v) for v in b) for b in r.boxes.xyxy.cpu().tolist()]
        verdicts.append(boxes_agree(boxes["cpu"], boxes[device]))
    judged = [v for v in verdicts if v is not None]
    return (all(judged) if judged else None), len(judged)


def scoring_agrees(gpu_map50, cpu_map50):
    """YOLO's scores on the GPU pick the best model and decide when to stop, and reported faults
    show them as zero. The GPU's score must not fall well below the CPU's on the same model."""
    return cpu_map50 < 0.001 or gpu_map50 >= 0.5 * cpu_map50


def gpu_vs_cpu_scoring(weights, device, batch, imgsz, n=40):
    """mAP50 of the same model on the same labelled images, on this device and on the CPU."""
    import glob

    from prepare_floorplancad import CLASSES
    from ultralytics import YOLO
    labels = [p for p in sorted(glob.glob(os.path.join(YOLO_DIR, "labels", "val", "*.txt")))
              if os.path.getsize(p) > 0][:n]
    for kind in ("images", "labels"):
        os.makedirs(os.path.join(YOLO_DIR, kind, "trial_val"), exist_ok=True)
    for path in labels:
        stem = os.path.splitext(os.path.basename(path))[0]
        shutil.copy(path, os.path.join(YOLO_DIR, "labels", "trial_val"))
        shutil.copy(os.path.join(YOLO_DIR, "images", "val", stem + ".jpg"), os.path.join(YOLO_DIR, "images", "trial_val"))
    data = os.path.join(YOLO_DIR, "trial_val.yaml")
    with open(data, "w", encoding="utf-8") as f:
        f.write(f"path: {YOLO_DIR}\ntrain: images/trial_val\nval: images/trial_val\nnames:\n")
        for i, c in enumerate(CLASSES):
            f.write(f"  {i}: {c}\n")
    scores = {}
    for d in dict.fromkeys((device, "cpu")):
        m = YOLO(weights).val(data=data, imgsz=imgsz, batch=batch, device=d, plots=False, verbose=False,
                              project=TRIAL_DIR, name="v", exist_ok=True)
        scores[d] = float(m.box.map50)
    return scores[device], scores["cpu"]


def run_trial(device, batch, epochs=TRIAL_EPOCHS, fraction=TRIAL_FRACTION, imgsz=IMGSZ):
    import glob

    from train_yolo import AUGMENT, pick_device
    from ultralytics import YOLO
    device = pick_device(device)
    shutil.rmtree(TRIAL_DIR, ignore_errors=True)
    YOLO("yolov8n.pt").train(data=os.path.join(YOLO_DIR, "data.yaml"), project=TRIAL_DIR, name="t", exist_ok=True,
                             seed=7, device=device, epochs=epochs, imgsz=imgsz, batch=batch,
                             fraction=fraction, val=False, plots=False, **AUGMENT)
    rows = _read_results(os.path.join(TRIAL_DIR, "t", "results.csv"))
    problem = losses_healthy(rows)
    images = sorted(glob.glob(os.path.join(YOLO_DIR, "images", "val", "*.jpg")))[:8]
    weights = os.path.join(TRIAL_DIR, "t", "weights", "last.pt")
    agree, judged = gpu_vs_cpu(weights, device, images)
    if problem is None and agree is False:
        problem = "the GPU and the CPU put boxes in different places"
    if problem is None and agree is None:
        problem = "no boxes to compare between the GPU and the CPU"
    gpu_map, cpu_map = gpu_vs_cpu_scoring(weights, device, batch, imgsz)
    if problem is None and not scoring_agrees(gpu_map, cpu_map):
        problem = f"the GPU scores the model {gpu_map:.3f} but the CPU scores it {cpu_map:.3f}"
    times = [float(r["time"]) for r in rows]
    epoch_s = (times[-1] - times[0]) / max(1, len(times) - 1) if len(times) > 1 else times[0]
    hours = epoch_s / fraction * 1.15 * EPOCHS / 3600.0      # +15%: validation each epoch
    return {"device": device, "batch": batch, "epoch_seconds_on_trial": round(epoch_s, 1),
            "estimated_hours_full_run": round(hours, 1), "images_compared": judged,
            "trial_map50_gpu": round(gpu_map, 4), "trial_map50_cpu": round(cpu_map, 4),
            "passed": problem is None, "problem": problem}


# ── commands ──────────────────────────────────────────────────────────────
def cmd_trial(a):
    os.makedirs(WORK, exist_ok=True)
    download(a.limit)
    convert(a.limit)
    check = label_check_image()
    result = run_trial(a.device, a.batch or default_batch(), imgsz=a.imgsz)
    with open(TRIAL_RESULT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    print("\n" + "=" * 60)
    print(f"Device: {result['device']}   Batch: {result['batch']}")
    print(f"Estimated full run: about {result['estimated_hours_full_run']} hours "
          "(rough; early stopping can shorten it)")
    print(f"Label check image: {check}  <- open it and check it (PLAN.md step 3)")
    if result["passed"]:
        print("TRIAL PASSED. If the estimate is acceptable, run:  bash run_mac.sh train")
    else:
        print(f"TRIAL FAILED: {result['problem']}\nDo NOT train on this device. See PLAN.md, 'If the trial fails'.")
    print("=" * 60)
    return 0 if result["passed"] else 1


def cmd_train(a):
    from train_yolo import pick_device, train
    if not os.path.isfile(TRIAL_RESULT):
        sys.exit("Run the trial first:  bash run_mac.sh trial")
    with open(TRIAL_RESULT, encoding="utf-8") as f:
        trial = json.load(f)
    device = pick_device(a.device)
    if not trial["passed"] or trial["device"] != device:
        sys.exit(f"STOP: no passed trial on '{device}'. Run:  bash run_mac.sh trial --device {device}")
    train(os.path.join(YOLO_DIR, "data.yaml"), PROJECT, epochs=a.epochs, imgsz=a.imgsz,
          batch=a.batch or trial["batch"], device=device)
    return cmd_finish(a)


def cmd_finish(a):
    from prepare_floorplancad import CLASSES
    from ultralytics import YOLO
    run = os.path.join(PROJECT, "door_window")
    best = os.path.join(run, "weights", "best.pt")
    if not os.path.isfile(best):
        sys.exit("No trained model yet. Run:  bash run_mac.sh train")
    # Final scores on the CPU, so they can't carry a GPU fault. This takes some minutes.
    m = YOLO(best).val(data=os.path.join(YOLO_DIR, "data.yaml"), imgsz=a.imgsz, split="val", device="cpu",
                       project=os.path.join(WORK, "final"), name="val", exist_ok=True)
    idx = m.ap_class_index.tolist()
    lines = [f"Final scores (validation drawings, measured on the CPU), {len(idx)} of {len(CLASSES)} classes"]
    for i, name in m.names.items():
        if i in idx:
            p, r, map50, _ = m.class_result(idx.index(i))
            lines.append(f"{name:<14} precision {p:.3f}  recall {r:.3f}  mAP50 {map50:.3f}")
        else:
            lines.append(f"{name:<14} no boxes in the validation drawings")
    lines.append(f"{'all':<14} mAP50 {m.box.map50:.3f}")
    report = "\n".join(lines)
    print(report)
    shutil.rmtree(SEND, ignore_errors=True)
    os.makedirs(SEND)
    shutil.copy(best, os.path.join(SEND, "dreamspace_door_window.pt"))
    with open(os.path.join(SEND, "scores.txt"), "w", encoding="utf-8") as f:
        f.write(report + "\n")
    for name in ("results.csv", "results.png", "args.yaml"):
        src = os.path.join(run, name)
        if os.path.isfile(src):
            shutil.copy(src, SEND)
    if os.path.isfile(TRIAL_RESULT):
        shutil.copy(TRIAL_RESULT, SEND)
    archive = shutil.make_archive(os.path.join(HERE, "dreamspace_results"), "zip", SEND)
    print(f"\nDONE. Send this one file back: {archive}")
    return 0


def cmd_status(a):
    path = os.path.join(PROJECT, "door_window", "results.csv")
    if not os.path.isfile(path):
        print("Training has not started.")
        return 0
    rows = _read_results(path)
    print(f"Epochs done: {len(rows)} of {a.epochs}   Hours so far: {float(rows[-1]['time']) / 3600:.1f}   "
          f"Latest mAP50: {rows[-1].get('metrics/mAP50(B)')}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["trial", "train", "finish", "status"])
    ap.add_argument("--device", default="auto", help="auto, mps or cpu")
    ap.add_argument("--batch", type=int, default=None, help="default: from this Mac's memory")
    ap.add_argument("--epochs", type=int, default=EPOCHS)
    ap.add_argument("--imgsz", type=int, default=IMGSZ, help=argparse.SUPPRESS)
    ap.add_argument("--limit", type=int, default=None, help=argparse.SUPPRESS)    # test this kit on a sample
    a = ap.parse_args()
    sys.exit({"trial": cmd_trial, "train": cmd_train, "finish": cmd_finish, "status": cmd_status}[a.command](a))


if __name__ == "__main__":
    main()
