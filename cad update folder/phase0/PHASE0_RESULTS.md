# Phase 0 — Feasibility Results

**Date:** 2026-09-25 · **Tool:** LibreDWG 0.14 (stable, win64, free/GPLv3) `dwg2dxf -y -o out.dxf in.dwg`
· **Reader:** ezdxf 1.4.4 `recover.readfile` · **Script:** `spike_convert.py`

## Verdict: GO ✅

Every sample that finished converted with LibreDWG and read back with **zero
audit errors** — including all 5 real floor plans, across AutoCAD 2004 / 2007 /
2010 / 2018 formats.

## Results

| # | File | AutoCAD | Size | Convert | Entities | Units | Audit errors | Thumbnail | What it is |
|---|---|---|---|---|---|---|---|---|---|
| 1 | Small-country-house-with-gazebo | 2018 (AC1032) | 0.8 MB | ✅ 0.4 s | 15,882 | mm | 0 | 12.8 s | **Floor plan** sheet + elevations, roof |
| 2 | Simple-Country-house-VER04 | 2004 (AC1018) | 2.7 MB | ✅ 1.1 s | 58,917 | in | 0 | 47.3 s | **Floor plan** sheet + elevations, section |
| 3 | Big-House-Patio-Terrace | 2004 (AC1018) | 0.3 MB | ✅ 0.1 s | 793 | m | 0 | 6.2 s | **Floor plans** (2 side by side) |
| 4 | THREE BEDROOM HOUSE PLAN *(inside zip)* | 2007 (AC1021) | 0.9 MB | ✅ 0.5 s | 2,355 | in | 0 | 10.1 s | **Floor plan** sheet + elevations, roof, foundation |
| 5 | Ishverbhai Punna | 2007 (AC1021) | 0.8 MB | ✅ 0.5 s | 10,498 | in | 0 | 13.3 s | **Floor plan** (living, bedrooms, baths labelled) |
| 6 | MANDIR mahadev location-6 | 2018 (AC1032) | 0.1 MB | ✅ 0.2 s | 198 | m | 0 | 2.0 s | Site / location plan — not a floor plan |
| 7 | LINE OUT | 2010 (AC1024) | 0.5 MB | ✅ 0.2 s | 32 | mm | 0 | 3.1 s | Structural column layout — not a floor plan |
| 8 | AUTOCAD_Library | 2004 (AC1018) | 19 MB | ✅ 9.0 s (→ 100 MB DXF) | 128,361 | mm | 0 | *still running at commit time* | Block library — not a floor plan |
| 9 | WORKING DRAWING … COLUMN & FOOTING | 2010 (AC1024) | 35 MB | *still running at commit time* | | | | | Structural — not a floor plan |

Rows 8–9 only stress-test large files; they don't affect the verdict.
The converter prints many warnings (up to ~1,700 lines per file) while ezdxf's
audit still finds 0 errors (it silently fixes 50–543 minor issues) — so warnings
are informational, not failures.

## Findings that shape Phase 1+

1. **Files are whole sheets, not single plans.** 4 of 5 floor-plan files also contain
   elevations, roof plans, sections; one has two floors side by side. The plan-picker
   step is essential, and clusters must be ranked "floor plan vs elevation" automatically.
2. **Stray far-away entities wreck the extents.** In *Ishverbhai Punna* and *Big House*,
   a lone object far from the drawing shrinks the real plan to a dot. Clustering must
   drop outliers; thumbnails/previews must use cluster extents, never whole-file extents.
3. **Wall layer names vary a lot:** `A-WALL` (2 files), `WALLS` (1), mostly layer `0`
   (gazebo house, 15k lines), **no wall layer at all** (Ishverbhai Punna: `fur`, `int`,
   `Presentation`, `0`). → geometry-based detection + the user review step are required.
4. **Units are set in every file** (m, mm, in) — none unitless. Header units work;
   the "infer/ask" fallback is still kept for other files.
5. **Room labels exist and often include sizes:** `BED ROOM - 3 12'-3"X14'-0"`,
   `LIVING ROOM 17'-9"X15'-0"`; some Spanish (`SALA FAMILIAR`, `MOBILIARIO` layer).
   → split label + dimension; mapping table needs a few non-English keywords.
6. **Full-sheet rendering is slow** (up to 47 s). → render only the chosen cluster, cache PNGs.
7. **Large files balloon** (19 MB DWG → 100 MB DXF, 128k entities). → keep the 50 MB
   upload cap, converter timeout, and skip heavy work outside the chosen cluster.
8. **Curved walls exist** (rounded bay in Simple Country House). → ARC handling from day one.
9. **Conversion is fast** (≤ 1.1 s for all floor plans; 9 s for the 19 MB library).
