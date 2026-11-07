"""Build DreamSpace_mac_training.zip from the tested files, so a colleague gets exactly these.
No datasets, models or client drawings go in. usage: python build_mac_kit.py"""
import os
import stat
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOP = "DreamSpace_mac_training"
FILES = {
    "mac/PLAN.md": "PLAN.md",
    "mac/run_mac.sh": "run_mac.sh",
    "mac/pipeline.py": "pipeline.py",
    "mac/requirements-mac.txt": "requirements-mac.txt",
    "prepare_floorplancad.py": "prepare_floorplancad.py",
    "train_yolo.py": "train_yolo.py",
    "dreamspace_train_door_window.ipynb": "colab/dreamspace_train_door_window.ipynb",
}

out = os.path.join(HERE, TOP + ".zip")
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
    for src, dst in FILES.items():
        with open(os.path.join(HERE, src), "rb") as f:
            data = f.read().replace(b"\r\n", b"\n")     # Mac line endings, or the .sh won't run
        info = zipfile.ZipInfo(f"{TOP}/{dst}", date_time=(2026, 11, 7, 12, 0, 0))
        info.compress_type = zipfile.ZIP_DEFLATED
        mode = 0o755 if dst.endswith(".sh") else 0o644
        info.external_attr = (stat.S_IFREG | mode) << 16
        z.writestr(info, data)
print(out, os.path.getsize(out), "bytes")
