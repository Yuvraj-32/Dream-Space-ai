# ML Room/Wall Detection — Upgrade Plan

> **STATUS: IMPLEMENTED (2026-07-18).** The CubiCasa5k engine is live behind
> `POST /detect/{file}?engine=ml` (also `engine=auto`; `classical` is the
> default). Code: `backend/ml_detector.py`. Model + weights under `backend/ml/`
> (git-ignored). Setup: `pip install -r requirements-ml.txt`. Tests:
> `tests/test_ml.py`. The frontend uses the ML engine via `DETECT_ENGINE` in
> `App.jsx`. The notes below are the original plan, kept for context.

Concrete plan to replace the classical CV room detector with a learned
segmentation model, as anticipated in `final_instructions.md` Phase 1
("upgrade to a fine-tuned model on **CubiCasa5k** later").

## Why

The classical pipeline in `detector.py` has a proven accuracy ceiling on
room segmentation, established empirically (2026-07-18):

- Rooms joined by open doorways merge into one flood-filled region.
- The door-sealing mitigation now shipped helps, but is gated by
  opening-detection completeness — every missed door merges two rooms.
- Furniture that survives as false walls needs continuous heuristic
  tuning that overfits to individual images.

A model trained on floor plans learns "this pixel region is a bedroom"
directly, sidestepping all of the above.

## Recommended model: CubiCasa5k

- Repo: `CubiCasa/CubiCasa5k` (Apache-2.0). Multi-task network (a
  modified hourglass/ResNet) that predicts, per pixel: **room type**,
  **wall/opening/icon** heatmaps, and junction points.
- Trained weights are published by the authors (~100–200 MB).
- Output is exactly what this project needs: room polygons + wall
  segments + door/window openings — the same three things the current
  `detect_floor_plan` returns.

Alternative if CubiCasa weights prove hard to source: a general semantic
segmentation backbone (e.g. `segmentation-models-pytorch` U-Net) fine-tuned
on CubiCasa5k data. More work; only if needed.

## Architecture — keep the API contract identical

The whole point is that **nothing downstream changes**. Frontend, the 2D
editor, and 3D extrusion all consume the current JSON schema
(`walls`/`rooms`/`openings` with `x1,y1,x2,y2`, `wall_type`, `polygon`,
`bbox`, `type`). The ML detector must emit the same shape.

```
POST /detect/{filename}
        │
        ▼
  detect_floor_plan(path, engine="classical" | "ml" | "auto")
        │
        ├─ engine="classical"  → current pipeline (unchanged, default)
        ├─ engine="ml"         → ml_detector.detect(path) → same JSON schema
        └─ engine="auto"       → try ml, fall back to classical on error
```

- Add `backend/ml_detector.py` with `detect(image_path) -> dict` returning
  the identical schema. Convert the model's room masks to polygons with the
  existing `cv2.findContours` + `approxPolyDP` code (already factored in
  `_detect_rooms`), so wall/room/opening formatting logic is shared.
- Keep classical as the default so a missing model or torch install never
  breaks the app (mirrors the existing `except ImportError` guard in
  `main.py`).

## Steps

1. **Dependencies** — add `torch`, `torchvision` to a *separate*
   `requirements-ml.txt` (they are large; don't force them on the classical
   deploy). Document CPU vs CUDA install.
2. **Weights** — script `backend/models/download_weights.py` that fetches
   the CubiCasa checkpoint to `backend/models/` (git-ignored). Never commit
   weights.
3. **Inference wrapper** — `ml_detector.py`: load model once (module-level
   singleton), preprocess (resize/normalize to the model's expected input),
   run, post-process heatmaps → walls/rooms/openings in our schema.
4. **Schema adapter** — reuse polygon/bbox/centroid construction from
   `_detect_rooms`; map the model's room-type labels into our `id`/`area`
   fields (bonus: we finally get real room *labels* — "bedroom", "kitchen").
5. **Wire the engine flag** through `main.py` `/detect` (query param
   `?engine=ml`, default `classical`).
6. **Test with the existing harness** — the same fixtures in
   `tests/fixtures/` and the snapshot mechanism work unchanged. Add ML
   ground-truth ranges to `tests/ground_truth.py` (the model should score
   far tighter). This is the payoff of building the harness first.
7. **Deploy considerations** — model load adds cold-start latency and RAM;
   inference on CPU is a few seconds per image (fine for this use case).
   For Render/Railway free tiers, watch the memory ceiling — may need a
   paid tier or a smaller/quantized model.

## Effort & risk

- **Effort:** ~2–4 focused days: 1 for wrapper + weights, 1 for schema
  adapter + flag, 1 for testing/tuning, buffer for deploy memory issues.
- **Main risk:** deployment footprint (torch + weights). Mitigated by the
  separate requirements file and the classical fallback — the app keeps
  working without the ML path.
- **Low risk to existing code:** the classical pipeline stays the default
  and untouched; ML is purely additive behind a flag.

## What NOT to do

- Don't retrain from scratch — use published CubiCasa weights.
- Don't drop the classical pipeline — it's the zero-dependency fallback and
  the deploy-light default.
- Don't change the `/detect` JSON schema — the frontend and 3D stages
  depend on it.
