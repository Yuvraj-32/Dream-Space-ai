"""Train the door/window detector. Starts from official YOLOv8n weights; if a run already
exists in the project folder (a Colab session ends, a laptop sleeps) it resumes it.

usage: python train_yolo.py --data <data.yaml> --project <folder> [--epochs 60] [--imgsz 800]
                            [--batch 16] [--device auto|mps|0|cpu]
"""
import argparse
import os

import torch
from ultralytics import YOLO

RUN = "door_window"
# Plans are line drawings with no "right way up" and no colour.
AUGMENT = dict(hsv_h=0.0, hsv_s=0.0, hsv_v=0.0, flipud=0.5, fliplr=0.5,
               degrees=0.0, shear=0.0, perspective=0.0, scale=0.3, translate=0.1, mosaic=0.5)


def pick_device(device="auto"):
    if device != "auto":
        return device
    if torch.cuda.is_available():
        return "0"       # first NVIDIA GPU, in YOLO's device naming
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def _unfinished(last):
    """A run in progress saves its optimizer and epoch. A finished run's last.pt is stripped of
    them, and resuming from it silently falls back to YOLO's default demo dataset."""
    ckpt = torch.load(last, map_location="cpu", weights_only=False)   # our own file, from this run
    return ckpt.get("optimizer") is not None and ckpt.get("epoch", -1) >= 0


def train(data, project, epochs=60, imgsz=800, batch=16, patience=15, device="auto"):
    device = pick_device(device)
    last = os.path.join(project, RUN, "weights", "last.pt")
    best = os.path.join(project, RUN, "weights", "best.pt")
    if os.path.isfile(last):
        if not _unfinished(last):
            print("This run already finished; nothing to do. Delete the run folder to train again.")
            return best
        YOLO(last).train(resume=True, device=device, batch=batch)
        return best
    YOLO("yolov8n.pt").train(
        data=data, project=project, name=RUN, exist_ok=True, seed=7, device=device,
        epochs=epochs, imgsz=imgsz, batch=batch, patience=patience, **AUGMENT,
    )
    return best


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--project", required=True)
    ap.add_argument("--epochs", type=int, default=60)
    ap.add_argument("--imgsz", type=int, default=800)
    ap.add_argument("--batch", type=int, default=16)
    ap.add_argument("--device", default="auto")
    a = ap.parse_args()
    print("best weights:", train(a.data, a.project, a.epochs, a.imgsz, a.batch, device=a.device))
