# DreamSpace AI

Upload a 2D floor-plan image → AI detects walls, rooms, doors, windows, and
built-in closets → review/edit in a 2D editor → walk through it in 3D with a
first-person view, a cinematic tour, and live material editing.

## Stack
- **Frontend:** React + Vite, Three.js (`@react-three/fiber`/`drei`) for 3D,
  Konva for the 2D editor.
- **Backend:** FastAPI + OpenCV. Two detection engines:
  - `classical` — pure OpenCV pipeline (`detector.py`), zero heavy deps.
  - `ml` (default) — CubiCasa5k segmentation model (`ml_detector.py`), accurate
    walls/rooms/openings + real-world measurements from the plan's dimension
    labels (`measurements.py`, EasyOCR).

## Quick start

```bash
# Frontend
cd frontend && npm install

# Backend
cd backend && python -m venv venv
venv\Scripts\python -m pip install -r requirements.txt
```

Then run both servers (from the project root):

```bat
start_servers.bat
```

Backend → http://localhost:8001, Frontend → http://localhost:5173.

> The `.bat` scripts are location-independent and launch uvicorn via
> `python -m uvicorn`, so they keep working if you move the project.

## Optional: ML engine (accurate detection + measurements)

The classical engine works out of the box. The `ml` engine needs extra,
git-ignored assets:

```bash
cd backend
venv\Scripts\python -m pip install -r requirements-ml.txt --index-url https://download.pytorch.org/whl/cpu

# 1. Clone the CubiCasa5k model repo (code + backbone weights)
git clone https://github.com/CubiCasa/CubiCasa5k.git ml/CubiCasa5k

# 2. Download the pretrained weights (~209MB) into ml/weights/
venv\Scripts\python -m gdown "https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK" -O ml/weights/model_best_val_loss_var.pkl
```

Runs CPU-only (~5–13s/image). See `backend/ML_UPGRADE_PLAN.md` for details.
The frontend requests the `ml` engine by default (`DETECT_ENGINE` in
`frontend/src/App.jsx`); it falls back to `classical` if the model is absent.

## Tests

```bash
cd backend && venv\Scripts\python -m pytest tests/ -q
```

`test_regression.py` covers the classical engine; `test_ml.py` covers the ML
engine (auto-skips if weights aren't downloaded); `test_measurements.py` pins
the scale-calibration guard.

## Tuning detection

`eval_detect.py` is the exploratory harness — it runs an engine over every plan
in the repo root plus `tests/fixtures/`, and writes an annotated overlay PNG
and the raw JSON per image to `backend/eval_out/` (git-ignored):

```bash
cd backend
venv\Scripts\python eval_detect.py --engine ml            # all plans
venv\Scripts\python eval_detect.py --engine both --measure
venv\Scripts\python eval_detect.py --tag before           # A/B two runs
venv\Scripts\python eval_detect.py --redraw               # re-render overlays only
```

Overlays draw openings **along** their host wall and rooms on top of walls —
without both, correct detections look broken.

Inference is ~30–60 s/image on CPU, dominated by 4× test-time rotation
averaging. `DREAMSPACE_ML_ROTATIONS=1` makes it ~3.5× faster, but measurably
degrades room-boundary quality (jagged edges the averaging removes), so 4 stays
the default.

### Scale calibration

With `?measure=true`, OCR reads the plan's printed dimension labels to set a
real-world scale. It only reports one when several samples **agree**; a plan
whose labels don't OCR cleanly returns `scale_ft_per_px: null` and the frontend
falls back to 1px=1cm. This is deliberate — the 3D stage sizes the whole world
from this number, so a wrong scale silently produces a cathedral-sized flat,
which is worse than an admitted unknown.
