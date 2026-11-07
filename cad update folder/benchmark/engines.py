"""Detection engines the benchmark can score. Each takes a bench_core.Plan and returns the
metre form (walls / doors / windows / rooms).

  vector    the CAD rules alone (image-AI assist switched off)
  pipeline  the CAD pipeline as the app runs it (rules + image-AI door referee)
  ml        the image model alone, on a black-on-white render of the plan
"""
import json
import os
import pickle

from bench_core import CACHE
from cad import ai_assist


def _with_ai(flag, fn):
    old = os.environ.get("DREAMSPACE_CAD_AI")
    os.environ["DREAMSPACE_CAD_AI"] = "1" if flag else "0"
    try:
        return fn()
    finally:
        if old is None:
            os.environ.pop("DREAMSPACE_CAD_AI", None)
        else:
            os.environ["DREAMSPACE_CAD_AI"] = old


def vector(plan):
    return plan.normalise(_with_ai(False, plan.detect_vector))


def pipeline(plan):
    return plan.normalise(_with_ai(True, plan.detect_vector))


def ml(plan):
    cdir = os.path.join(CACHE, "ml")
    os.makedirs(cdir, exist_ok=True)
    stem = os.path.join(cdir, f"{plan.label['plan']}_{plan.insp['session_id']}_{plan.cluster['id']}")
    if not os.path.isfile(stem + ".json"):
        with open(os.path.join(plan.sdir, "state.pkl"), "rb") as f:
            state = pickle.load(f)
        x0, _, _, y1 = plan.cluster["bbox"]
        off = (plan.img_w - plan.W_m * plan.ppm) / 2.0
        ai_assist.render_linework(state["records"], state["members"][plan.cluster["id"]], x0, y1,
                                  plan.ppm * plan.mpu, off, plan.img_w, plan.img_h, stem + ".png")
    det = ai_assist.image_ai(stem + ".png", stem + ".json")
    return plan.normalise(det)


ENGINES = {"vector": vector, "pipeline": pipeline, "ml": ml}
