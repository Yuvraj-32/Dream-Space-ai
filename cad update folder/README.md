# CAD input (.dwg / .dxf) for DreamSpace

Everything for AutoCAD input lives in this folder. The JPG/PNG pipeline is untouched; the
only shared files with CAD hook-ins are `backend/main.py`, `backend/requirements.txt`,
`frontend/vite.config.js`, `frontend/src/App.jsx`, `frontend/src/components/UploadPanel.jsx`,
`SceneCanvas.jsx` (camera framing, CAD only) and `DetectionStats.jsx` (an extra info block that
shows for CAD results only).

Everything here is free software: no paid services, no API keys.

## How it works

1. **Upload** a `.dwg` or `.dxf` (up to 50 MB) in the normal upload panel.
2. **Inspect** (`POST /cad/inspect/{file}`): DWG is converted to DXF with LibreDWG, the drawing is
   read, units are worked out from the geometry, and the drawings in the file (floor plans,
   elevations, ...) are found. A progress bar polls `GET /cad/progress/{file}`.
3. **Review**: pick the floor plan, check layer roles (walls / doors / windows / room names) and units.
4. **Detect** (`POST /cad/detect/{file}`): exact walls, doors, windows and rooms, returned in the
   same JSON shape as the image pipeline, so the 2D editor and 3D walkthrough work unchanged.

Details, design decisions and the accuracy log: [CAD_INPUT_PLAN.md](CAD_INPUT_PLAN.md).

## Install

Python packages (already in `backend/requirements.txt`):

```bash
cd backend
pip install -r requirements.txt     # includes ezdxf; shapely, httpx, opencv, numpy
```

DWG files need **LibreDWG** (free, GPLv3). DXF files do not need it.

- Windows: download the LibreDWG release zip from https://www.gnu.org/software/libredwg/ and unpack
  it to `C:\tools\libredwg\` so that `C:\tools\libredwg\dwg2dxf.exe` exists.
- Elsewhere: install the `libredwg` package so `dwg2dxf` is on your `PATH`.
- Any other location: set the environment variable `LIBREDWG_DWG2DXF` to the full path of `dwg2dxf`.

Check it: start the backend and open `http://localhost:8001/cad/health`.

Optional environment variable: `CAD_CONVERT_TIMEOUT_S` (default 120) caps one DWG conversion.

## Run the tests

From `backend/`:

```bash
venv/Scripts/python.exe -m pytest "../cad update folder/backend/cad/tests" tests -q -p no:cacheprovider
```

The first path is the CAD suite (synthetic DXF files, no binaries needed); `tests` is the existing
image-pipeline regression suite, which must stay green.

## Limits worth knowing

- LibreDWG can silently drop entities in some newer DWG files. If a drawing comes out empty or
  without walls the review step says so; saving the file as DXF from AutoCAD always works.
- Huge files (tens of MB of block libraries) can take a few minutes to read; the progress bar shows
  which step is running. Exporting just the floor plan as DXF is much faster.
- Room names come from the drawing's own text. Rooms with no label stay `undefined`, apart from
  a few documented fallbacks (stairs, the biggest unlabelled space, shower stalls beside a bath).
