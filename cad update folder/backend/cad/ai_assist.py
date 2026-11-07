"""Image-AI assist for CAD detection.

The CAD rules read the drawing's exact geometry; the image model (CubiCasa5k, the
JPG pipeline's detector, used unchanged) reads the plan the way a person looks at
it. On CAD drawings the image model alone is clearly worse (benchmark/, 10
labelled plans: doors F1 77 vs 87, windows 64 vs 93, rooms typed 14 vs 52 of 79),
so it is used in two narrow ways:

* Door referee: every quarter swing allows exactly two doorways (hinge -> either
  end of the arc). The rules choose one; where the image model clearly prefers the
  other, take that one. The door still sits exactly where the drawing puts it, the
  model only breaks the tie. Benchmark: doors F1 87.4 -> 95.6, nothing else changes.
* Last-resort fallback: if the rules find no rooms at all but the model finds some,
  its whole result is used (with a warning) instead of an empty plan.

Turned off with DREAMSPACE_CAD_AI=0; silently skipped when torch or the model
weights are missing, so CAD detection never depends on it.
"""
import json
import logging
import math
import os
import time

import cv2
import numpy as np

log = logging.getLogger(__name__)

SKIP_KINDS = {"HATCH", "TEXT", "MTEXT", "DIMENSION", "ATTRIB", "ATTDEF"}
OWN_M = 0.35       # a rules door this close to a doorway candidate is that candidate's door
REACH_M = 0.9      # an AI door further than this from a candidate says nothing about it
PREFER_RATIO = 0.6  # the AI must be this much closer (ratio) to the other candidate...
PREFER_MIN_M = 0.1  # ...and at least this much closer in metres
FALLBACK_MIN_ROOMS = 2


def enabled():
    return os.environ.get("DREAMSPACE_CAD_AI", "1") != "0"


def render_linework(records, members, x0, y1, scale, off, width, height, path):
    """The drawing's own lines, black on white, in the preview's pixel space."""
    img = np.full((height, width, 3), 255, np.uint8)
    segs = [s for i in members if records[i].segs and records[i].kind not in SKIP_KINDS for s in records[i].segs]
    if segs:
        s = np.asarray(segs, dtype=np.float64)
        pts = np.empty((len(s), 2, 2), dtype=np.int32)  # contiguous: OpenCV 5 rejects strided views
        pts[:, :, 0] = np.round((s[:, [0, 2]] - x0) * scale + off)
        pts[:, :, 1] = np.round((y1 - s[:, [1, 3]]) * scale + off)
        cv2.polylines(img, list(pts), isClosed=False, color=(0, 0, 0), thickness=2, lineType=cv2.LINE_AA)
    cv2.imwrite(path, img)


def image_ai(render, cache_json):
    """Run the image model on a render (cached); None if the model can't run here."""
    if os.path.isfile(cache_json):
        try:
            with open(cache_json, encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):      # damaged cache: run the model again
            pass
    try:
        from ml_detector import detect_floor_plan_ml   # backend/ (already on sys.path via main.py)
        t = time.time()
        det = detect_floor_plan_ml(render)
        det["seconds"] = round(time.time() - t, 1)
    except Exception as exc:  # torch / weights missing, or the model failed: CAD rules alone
        log.info("CAD image-AI assist unavailable: %s", exc)
        return None
    with open(cache_json, "w", encoding="utf-8") as f:
        json.dump(det, f)
    return det


def _door_like(a):
    return 80.0 <= a[3] <= 100.0 and 0.5 <= a[2] <= 1.3


def _prefers(near, far):
    """The AI clearly prefers the candidate it is `near` over the one it is `far` from."""
    return near <= PREFER_RATIO * far and far - near >= PREFER_MIN_M


def _nearest(pt, items):
    return min((math.hypot(pt[0] - o[0], pt[1] - o[1]) for o in items), default=math.inf)


def merge_chords(chords, ang_tol=10.0, line_tol=0.15, gap=0.05):
    """Join doorway chords on one line that touch or overlap (a double door, or a main
    door plus a safety door in the same opening) into one opening."""
    chords = [list(c) for c in chords]
    i = 0
    while i < len(chords):
        j = i + 1
        while j < len(chords):
            a, b = chords[i], chords[j]
            ax, ay = a[2] - a[0], a[3] - a[1]
            la = math.hypot(ax, ay)
            lb = math.hypot(b[2] - b[0], b[3] - b[1])
            ux, uy = ax / la, ay / la
            cosang = abs(ux * (b[2] - b[0]) + uy * (b[3] - b[1])) / lb
            t0, t1 = sorted([(b[0] - a[0]) * ux + (b[1] - a[1]) * uy, (b[2] - a[0]) * ux + (b[3] - a[1]) * uy])
            if (cosang >= math.cos(math.radians(ang_tol))
                    and abs((b[0] - a[0]) * -uy + (b[1] - a[1]) * ux) <= line_tol
                    and t0 <= la + gap and t1 >= -gap):
                lo, hi = min(0.0, t0), max(la, t1)
                chords[i] = [a[0] + ux * lo, a[1] + uy * lo, a[0] + ux * hi, a[1] + uy * hi]
                del chords[j]
                j = i + 1
                continue
            j += 1
        i += 1
    return chords


def referee_doors(openings, arcs, ai_doors):
    """openings: pipeline openings (metres). arcs: swing arcs (cx,cy,r,sweep,sx,sy,ex,ey[,..]).
    ai_doors: [(x, y)] in the same metres. Returns (openings, number of doors moved)."""
    doors = [k for k, o in enumerate(openings) if o["type"] == "door"]
    decisions, replaced, seen = [], set(), set()
    for a in arcs:
        key = tuple(round(v, 3) for v in a[:8])
        if not _door_like(a) or key in seen:
            continue
        seen.add(key)
        hinge = (a[0], a[1])
        ends = [(a[4], a[5]), (a[6], a[7])]
        centres = [((hinge[0] + e[0]) / 2, (hinge[1] + e[1]) / 2) for e in ends]
        near_ai = [d for d in ai_doors if math.hypot(d[0] - hinge[0], d[1] - hinge[1]) <= a[2] + 0.6]
        vd = [_nearest(c, [(openings[k]["x"], openings[k]["y"]) for k in doors]) for c in centres]
        md = [_nearest(c, near_ai) for c in centres]
        sup = [d <= OWN_M for d in vd]
        choice, flip = None, False
        if sup[0] != sup[1]:
            choice = 0 if sup[0] else 1
            other = 1 - choice
            if md[other] <= REACH_M and _prefers(md[other], md[choice]):
                choice, flip = other, True
        elif min(md) <= REACH_M and _prefers(min(md), max(md)):
            choice, flip = (0 if md[0] < md[1] else 1), True      # rules had no clear doorway here
        if choice is None:
            continue
        owned = {k for k in doors
                 if min(math.hypot(openings[k]["x"] - c[0], openings[k]["y"] - c[1]) for c in centres) <= OWN_M
                 or math.hypot(openings[k]["x"] - hinge[0], openings[k]["y"] - hinge[1]) <= 0.6}
        decisions.append((owned, (hinge[0], hinge[1], ends[choice][0], ends[choice][1])))
        if flip:
            replaced |= owned
    if not replaced:
        return openings, 0
    # Every arc whose rules door is being replaced is re-emitted from its chosen chord
    # (a merged double door owns two arcs; both must come back).
    chords = [chord for owned, chord in decisions if owned & replaced]
    out = [o for k, o in enumerate(openings) if k not in replaced]
    for c in merge_chords(chords):
        out.append({"type": "door", "x": (c[0] + c[2]) / 2.0, "y": (c[1] + c[3]) / 2.0,
                    "width": math.hypot(c[2] - c[0], c[3] - c[1]), "chord": tuple(c), "source": "ai_referee"})
    return out, len(replaced)
