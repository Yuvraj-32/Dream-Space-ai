"""Shared helpers for the CAD detection benchmark.

Ground truth lives in labels/<plan>.json in METRES measured from the plan's own
corner (`plan_bbox`, drawing units), y up. It does not depend on how the
pipeline numbers or crops its drawings, so labels survive clustering changes.

Every engine's output is normalised to the same metre form before scoring:
  walls   [(x1, y1, x2, y2, thickness_m)]   centre lines
  doors   [(x, y, width_m)]                 opening centre
  windows [(x, y, width_m)]
  rooms   [{"type", "label", "poly": [(x, y), ...]}]
"""
import json
import math
import os
import sys
import zipfile

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
for p in (os.path.join(HERE, "..", "backend"), os.path.join(REPO, "backend")):
    if p not in sys.path:
        sys.path.insert(0, p)

from cad.detect import MARGIN_M, TARGET_LONG_PX, detect_file  # noqa: E402
from cad.loader import NAME_TO_M                              # noqa: E402
from cad.pipeline import inspect_file, session_dir            # noqa: E402

CACHE = os.path.join(HERE, ".cache")
LABELS = os.path.join(HERE, "labels")
OUT = os.path.join(HERE, "out")


def source_path(name):
    """Sample drawings live (untracked) in the repo root; "archive.zip::member" is extracted to the cache."""
    if "::" in name:
        arc, member = name.split("::", 1)
        dest = os.path.join(CACHE, "unzipped")
        path = os.path.join(dest, member)
        if not os.path.isfile(path):
            with zipfile.ZipFile(os.path.join(REPO, arc)) as z:
                z.extract(member, dest)
        return path
    return os.path.join(REPO, name)


def load_labels(only=None):
    out = []
    for fn in sorted(os.listdir(LABELS)):
        if fn.endswith(".json") and (not only or fn[:-5] in only):
            with open(os.path.join(LABELS, fn), encoding="utf-8") as f:
                out.append(json.load(f))
    return out


def _iou(a, b):
    ix = max(0.0, min(a[2], b[2]) - max(a[0], b[0]))
    iy = max(0.0, min(a[3], b[3]) - max(a[1], b[1]))
    inter = ix * iy
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union > 0 else 0.0


class Plan:
    """One labelled drawing: finds the pipeline's matching cluster and converts coordinates."""

    def __init__(self, label):
        self.label = label
        self.src = source_path(label["file"])
        self.insp = inspect_file(self.src, CACHE)
        self.units = label.get("units")
        self.mpu = NAME_TO_M[self.units] if self.units else self.insp["units"]["metres_per_unit"]
        pb = label["plan_bbox"]
        best = max(self.insp["clusters"], key=lambda c: _iou(c["bbox"], pb))
        if _iou(best["bbox"], pb) < 0.5:
            raise RuntimeError(f"{label['plan']}: no drawing matches the labelled plan any more")
        self.cluster = best
        x0, y0, x1, y1 = best["bbox"]
        self.W_m, self.H_m = (x1 - x0) * self.mpu, (y1 - y0) * self.mpu
        self.ppm = TARGET_LONG_PX / (max(self.W_m, self.H_m) + 2 * MARGIN_M)
        self.img_w = int(math.ceil((self.W_m + 2 * MARGIN_M) * self.ppm))
        self.img_h = int(math.ceil((self.H_m + 2 * MARGIN_M) * self.ppm))
        # label origin -> cluster origin offset, metres
        self.dx = (x0 - pb[0]) * self.mpu
        self.dy = (y0 - pb[1]) * self.mpu

    @property
    def sdir(self):
        return session_dir(CACHE, self.insp["session_id"])

    def px_to_m(self, px, py):
        return (px / self.ppm - MARGIN_M + self.dx, self.H_m + MARGIN_M - py / self.ppm + self.dy)

    def m_to_px(self, x, y):
        return (int(round((x - self.dx + MARGIN_M) * self.ppm)),
                int(round((self.H_m + MARGIN_M - (y - self.dy)) * self.ppm)))

    def detect_vector(self):
        return detect_file(self.src, CACHE, cluster_id=self.cluster["id"], units_name=self.units)

    def normalise(self, det):
        """Pipeline JSON (pixel space of this plan's preview) -> metre form."""
        walls = []
        for w in det["walls"]:
            a, b = self.px_to_m(w["x1"], w["y1"]), self.px_to_m(w["x2"], w["y2"])
            t = w.get("thickness_m") or w.get("thickness", 0) / self.ppm
            walls.append((*a, *b, t))
        doors, windows = [], []
        for o in det["openings"]:
            x, y = self.px_to_m(o["x"], o["y"])
            wd = o.get("width_m") or o.get("width_px", 0) / self.ppm
            (doors if o["type"] == "door" else windows).append((x, y, wd))
        rooms = [{"type": r["type"], "label": r.get("label"),
                  "poly": [self.px_to_m(*p) for p in r["polygon"]]} for r in det["rooms"]]
        return {"walls": walls, "doors": doors, "windows": windows, "rooms": rooms}


# ── scoring ──────────────────────────────────────────────────────────────
def match_points(gt, pred, tol):
    """Greedy one-to-one match of (x, y, w) items; a pair counts if the centres are
    within tol(gt_item) metres. Returns (matched pairs, unmatched gt idx, unmatched pred idx)."""
    cand = []
    for i, g in enumerate(gt):
        for j, p in enumerate(pred):
            d = math.hypot(g[0] - p[0], g[1] - p[1])
            if d <= tol(g):
                cand.append((d, i, j))
    cand.sort()
    used_g, used_p, pairs = set(), set(), []
    for d, i, j in cand:
        if i in used_g or j in used_p:
            continue
        used_g.add(i)
        used_p.add(j)
        pairs.append((i, j, d))
    return pairs, [i for i in range(len(gt)) if i not in used_g], [j for j in range(len(pred)) if j not in used_p]


def opening_tol(g):
    return max(0.5, 0.6 * g[2])


def _samples(segs, step):
    pts = []
    for s in segs:
        n = max(1, int(math.hypot(s[2] - s[0], s[3] - s[1]) / step))
        for k in range(n + 1):
            t = k / n
            pts.append((s[0] + t * (s[2] - s[0]), s[1] + t * (s[3] - s[1])))
    return np.asarray(pts, dtype=np.float64).reshape(-1, 2)


def _min_dist(pts, segs):
    """Distance from each point to the nearest segment (vectorised)."""
    if not len(pts) or not segs:
        return np.full(len(pts), np.inf)
    S = np.asarray([s[:4] for s in segs], dtype=np.float64)
    a, b = S[:, :2], S[:, 2:4]
    ab = b - a
    L2 = np.maximum((ab ** 2).sum(1), 1e-12)
    best = np.full(len(pts), np.inf)
    for i in range(0, len(pts), 2000):
        p = pts[i:i + 2000, None, :]
        t = np.clip(((p - a) * ab).sum(2) / L2, 0.0, 1.0)
        q = a + t[..., None] * ab
        best[i:i + 2000] = np.sqrt(((p - q) ** 2).sum(2)).min(1)
    return best


def wall_scores(gt_walls, pred_walls, tol=0.2, step=0.05):
    """Length-based: recall = share of true wall length with a detected wall within tol;
    precision = share of detected wall length lying on a true wall."""
    g = _samples(gt_walls, step)
    p = _samples(pred_walls, step)
    rec = float((_min_dist(g, pred_walls) <= tol).mean()) if len(g) else 1.0
    prec = float((_min_dist(p, gt_walls) <= tol).mean()) if len(p) else 0.0
    return {"recall": rec, "precision": prec, "gt_m": round(len(g) * step, 1), "pred_m": round(len(p) * step, 1)}


def _inside(pt, poly):
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def room_scores(gt_rooms, pred_rooms):
    """Each labelled room: is its label point inside a detected room (found), with the
    right type (typed), and does that detected room swallow another labelled room (merged)?
    Rooms sharing a "zone" (open plan, no wall drawn between them) may share one detected
    room without counting as merged; their type only has to match one of the zone's types."""
    hits = []
    for g in gt_rooms:
        idx = next((k for k, r in enumerate(pred_rooms) if _inside(g["at"], r["poly"])), None)
        hits.append(idx)
    found = sum(1 for h in hits if h is not None)

    def zone_types(g):
        z = g.get("zone")
        return {o["type"] for o in gt_rooms if z and o.get("zone") == z} or {g["type"]}

    typed = sum(1 for g, h in zip(gt_rooms, hits) if h is not None and pred_rooms[h]["type"] in zone_types(g))
    merged = sum(1 for k, h in enumerate(hits)
                 if h is not None and any(j != k and hits[j] == h and not (gt_rooms[k].get("zone")
                                          and gt_rooms[k].get("zone") == gt_rooms[j].get("zone"))
                                          for j in range(len(hits))))
    dims = []
    for g, h in zip(gt_rooms, hits):
        if h is None or not g.get("dims_ft"):
            continue
        xs = [p[0] for p in pred_rooms[h]["poly"]]
        ys = [p[1] for p in pred_rooms[h]["poly"]]
        got = sorted([(max(xs) - min(xs)) / 0.3048, (max(ys) - min(ys)) / 0.3048])
        lab = sorted(g["dims_ft"])
        dims.append(max(abs(a - b) / b for a, b in zip(got, lab)) * 100.0)
    return {"rooms": len(gt_rooms), "found": found, "typed": typed, "merged": merged,
            "dim_err_pct": sorted(dims)}


def score(label, pred):
    """Scores per category; categories listed in label["skip"] (ground truth unknown) are left out."""
    skip = set(label.get("skip", ()))
    out = {}
    for key in ("doors", "windows"):
        if key in skip:
            continue
        gt = [(d["at"][0], d["at"][1], d["w"]) for d in label[key]]
        pairs, miss, extra = match_points(gt, pred[key], opening_tol)
        out[key] = {"tp": len(pairs), "fn": len(miss), "fp": len(extra), "missed": miss, "false": extra}
    if "walls" not in skip:
        out["walls"] = wall_scores([(*w["a"], *w["b"], w.get("t", 0.2)) for w in label["walls"]], pred["walls"])
    if "rooms" not in skip and label["rooms"]:
        out["rooms"] = room_scores(label["rooms"], pred["rooms"])
    return out


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 1.0
    r = tp / (tp + fn) if tp + fn else 1.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f
