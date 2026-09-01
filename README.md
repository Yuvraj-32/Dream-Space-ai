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
cd frontend && npm install && npm run textures   # textures = wall PBR maps

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

## Wall materials (PBR textures)

The 3D walls are textured from real CC0 PBR scans (ambientCG), not generated
maps. The files live in `frontend/public/textures/<material>/` as
`color.jpg` + `normal.jpg` (OpenGL convention) + `roughness.jpg`; see
`frontend/public/textures/LICENSE.md` for the exact asset list, sources, and
each scan's real-world size.

The `.jpg` maps are **git-ignored** (same convention as the ML weights) — the
manifest and licence are tracked, the binaries are fetched on demand:

```bash
cd frontend && npm run textures
```

The script has no npm dependencies and skips anything already present. Missing
maps are non-fatal — a material without them falls back to its scalar
roughness/metalness and logs one warning, so a fresh clone still runs.

The material library itself is `frontend/src/materials/`:
`registry.js` (what each material is, including its physical tile size),
`textureManager.js` (loading + per-repeat texture caching),
`wallSurface.js` (per-face tiling for a wall box).

## Tests

```bash
cd backend && venv\Scripts\python -m pytest tests/ -q
```

`test_regression.py` covers the classical engine; `test_ml.py` covers the ML
engine (auto-skips if weights aren't downloaded).
