"""Build the Colab notebook from the two tested scripts, so what runs on Colab is exactly
what was tested here. usage: python build_notebook.py"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ULTRALYTICS = "8.4.202"     # the version the smoke test ran on


def md(text):
    return {"cell_type": "markdown", "metadata": {}, "source": text.strip("\n").splitlines(True)}


def code(text):
    return {"cell_type": "code", "metadata": {}, "execution_count": None, "outputs": [],
            "source": text.strip("\n").splitlines(True)}


def writer(name):
    """A cell that writes one tested script to /content, byte for byte."""
    with open(os.path.join(HERE, name), encoding="utf-8") as f:
        body = f.read()
    return code(f"open('/content/{name}', 'w', encoding='utf-8').write({body!r})")


cells = [
    md("""
# DreamSpace: train the door & window detector

Trains a small YOLO model on FloorPlanCAD to find single doors, double doors, sliding doors and
windows. Free: it uses Colab's free GPU and your Google Drive. **Nothing here needs a card. If anything
asks for payment, stop.**

**How to run**
1. Menu **Runtime > Change runtime type > T4 GPU**, then Save.
2. Menu **Runtime > Run all**. Colab asks to access your Google Drive: allow it (progress is saved there).
3. Keep the tab open. Expect 2-4 hours.
4. If the session ends, just press **Run all** again: training resumes from the last epoch.
5. When finished, download `DreamSpace_training/dreamspace_door_window.pt` from your Google Drive
   and put it in `cad update folder/training/` in the project.

Dataset licence: FloorPlanCAD is non-commercial (CC BY-NC 4.0). YOLO is AGPL-3.0.
"""),
    md("## 1. Check the GPU"),
    code("""
import torch
assert torch.cuda.is_available(), "No GPU: use Runtime > Change runtime type > T4 GPU, then Run all again."
print("GPU:", torch.cuda.get_device_name(0))
"""),
    md("## 2. Install YOLO and connect Google Drive"),
    code(f"""
!pip -q install ultralytics=={ULTRALYTICS} huggingface_hub
from google.colab import drive
drive.mount('/content/drive')
PROJECT = '/content/drive/MyDrive/DreamSpace_training'
!mkdir -p "$PROJECT"
"""),
    md("## 3. Download FloorPlanCAD (454 MB, about 5,300 plan images)"),
    code("""
from huggingface_hub import snapshot_download
snapshot_download(repo_id='Voxel51/FloorPlanCAD', repo_type='dataset', local_dir='/content/fpc',
                  allow_patterns=['samples.json', 'data/*'], max_workers=8)
!ls /content/fpc/data | wc -l
"""),
    md("""
## 4. Convert to YOLO format

This copy's class names are wrong for doors and windows, so the script corrects them (see its header).
"""),
    writer("prepare_floorplancad.py"),
    code("""
!python /content/prepare_floorplancad.py --root /content/fpc --out /content/yolo
"""),
    md("## 5. Train (2-4 hours; re-run resumes if the session ends)"),
    writer("train_yolo.py"),
    code("""
!cd /content && python /content/train_yolo.py --data /content/yolo/data.yaml --project "$PROJECT" --epochs 60 --imgsz 800 --batch 16
"""),
    md("## 6. Final scores, and save the model to your Drive"),
    code("""
import shutil
from ultralytics import YOLO
best = f'{PROJECT}/door_window/weights/best.pt'
metrics = YOLO(best).val(data='/content/yolo/data.yaml', imgsz=800, split='val')
for i, name in metrics.names.items():
    p, r, map50, map5095 = metrics.class_result(metrics.ap_class_index.tolist().index(i))
    print(f'{name:<14} precision {p:.3f}  recall {r:.3f}  mAP50 {map50:.3f}')
shutil.copy(best, f'{PROJECT}/dreamspace_door_window.pt')
print('Saved: Google Drive > DreamSpace_training > dreamspace_door_window.pt  (download this file)')
"""),
]

nb = {"cells": cells, "metadata": {"accelerator": "GPU", "colab": {"gpuType": "T4", "name": "dreamspace_train_door_window"},
                                    "kernelspec": {"display_name": "Python 3", "name": "python3"},
                                    "language_info": {"name": "python"}},
      "nbformat": 4, "nbformat_minor": 5}
out = os.path.join(HERE, "dreamspace_train_door_window.ipynb")
with open(out, "w", encoding="utf-8") as f:
    json.dump(nb, f, indent=1)
print(out, len(cells), "cells")
