# CAD detection benchmark

Measures CAD detection against hand-checked ground truth, so every change is scored
instead of judged by eye.

```bash
cd "cad update folder/benchmark"
..\..\backend\venv\Scripts\python score.py vector pipeline ml --details
```

- `vector`: the CAD rules alone. `pipeline`: what the app runs (the rules plus the
  image-AI door referee, `backend/cad/ai_assist.py`). `ml`: the image model alone, run on
  a black-on-white render of the plan.
- Doors and windows are scored by precision and recall. A detection matches a labelled
  opening if their centres are within max(0.5 m, 0.6 x width). Walls are scored by length:
  the share of true wall length that has a detected wall within 0.2 m, and the reverse.
  Rooms are scored per printed room label: whether it falls inside a detected room
  (found), whether that room has the right type (typed), and whether one detected room
  holds two labelled rooms (merged). Rooms that share a `zone` are open plan, so they
  may share one detected room.
- The sample drawings are not in git. They live in the repo root (see the handoff zip).
  The `.cache/` and `out/` folders are git-ignored.

## Labels (`labels/<plan>.json`)

Coordinates are metres from the plan's own corner (`plan_bbox`, in drawing units), with
y pointing up. A label lists walls (centre lines), doors and windows (opening centre and
width), and rooms (label point, type, and printed size if given).

A new plan is added like this:
1. Run `python draft_labels.py <slug> <file> <cluster>`. This writes a draft from the
   current detection and the drawing's own room labels, plus `out/<slug>_review.png`.
2. Check the review image against the drawing, and correct it with
   `review.edit(slug, note=..., remove=[...], walls=[...], doors=[...], ...)`. Every
   correction adds a note to the file.
3. A category that can't be judged from the drawing goes into `"skip"`. A plan that
   can't be judged at all gets `"status": "excluded"`.

Note: the wall ground truth started from the detector's own output and was then
corrected by eye, which flatters wall precision a little. Doors, windows and rooms were
checked against independent evidence: swing arcs, glazing symbols and printed labels.

## Results (10 plans: 76 doors, 62 windows, 79 labelled rooms; Nov 2026)

| engine   | doors P / R / F1   | windows P / R / F1 | walls P / R | rooms found / typed / merged |
|----------|--------------------|--------------------|-------------|------------------------------|
| vector   | 89.4 / 85.5 / 87.4 | 96.5 / 90.2 / 93.2 | 97.7 / 97.6 | 58 / 52 / 10                 |
| ml       | 77.9 / 76.8 / 77.4 | 60.3 / 67.2 / 63.6 | 81.6 / 82.2 | 54 / 14 / 26                 |
| pipeline | 97.0 / 94.2 / 95.6 | 96.5 / 90.2 / 93.2 | 97.7 / 97.6 | 58 / 52 / 10                 |
