"""Score detection engines against the reviewed labels.

usage: python score.py [engine ...] [--plans a,b] [--details]
engines: vector (current CAD pipeline), ml (CubiCasa on a render of the plan), fused
Writes out/scores_<engine>.json and prints one table per engine.
"""
import json
import os
import sys

from bench_core import OUT, Plan, load_labels, prf, score
import engines


def fmt(p, r):
    return f"{p * 100:5.1f} {r * 100:5.1f}"


def run(engine, labels, details):
    rows, tot = [], {"doors": [0, 0, 0], "windows": [0, 0, 0], "wall_g": 0.0, "wall_gc": 0.0,
                     "wall_p": 0.0, "wall_pc": 0.0, "rooms": [0, 0, 0, 0], "dims": []}
    report = {}
    for lab in labels:
        plan = Plan(lab)
        pred = engines.ENGINES[engine](plan)
        s = score(lab, pred)
        report[lab["plan"]] = s
        for k in ("doors", "windows"):
            if k in s:
                for i, f in enumerate(("tp", "fp", "fn")):
                    tot[k][i] += s[k][f]
        if "walls" in s:
            w = s["walls"]
            tot["wall_g"] += w["gt_m"]
            tot["wall_gc"] += w["gt_m"] * w["recall"]
            tot["wall_p"] += w["pred_m"]
            tot["wall_pc"] += w["pred_m"] * w["precision"]
        if "rooms" in s:
            r = s["rooms"]
            for i, f in enumerate(("rooms", "found", "typed", "merged")):
                tot["rooms"][i] += r[f]
            tot["dims"] += r["dim_err_pct"]
        rows.append((lab["plan"], s))
        if details:
            for k in ("doors", "windows"):
                if k in s and (s[k]["missed"] or s[k]["false"]):
                    gt = lab[k]
                    print(f"   {lab['plan']:<12} {k}: missed {[gt[i]['id'] for i in s[k]['missed']]}"
                          f"  false at {[tuple(round(v, 2) for v in pred[k][j][:2]) for j in s[k]['false']]}")

    print(f"\n== {engine}")
    print(f"{'plan':<13}{'doors P   R':>13}{'windows P   R':>15}{'walls P   R':>13}  rooms found/typed/merged of n")
    for name, s in rows:
        d = fmt(*prf(s['doors']['tp'], s['doors']['fp'], s['doors']['fn'])[:2]) if "doors" in s else "    -     -"
        wn = fmt(*prf(s['windows']['tp'], s['windows']['fp'], s['windows']['fn'])[:2]) if "windows" in s else "    -     -"
        wl = fmt(s["walls"]["precision"], s["walls"]["recall"]) if "walls" in s else "    -     -"
        rm = (f"{s['rooms']['found']}/{s['rooms']['typed']}/{s['rooms']['merged']} of {s['rooms']['rooms']}"
              if "rooms" in s else "-")
        print(f"{name:<13}{d:>13}{wn:>15}{wl:>13}  {rm}")
    dp, dr, df = prf(*tot["doors"])
    wp, wr, wf = prf(*tot["windows"])
    walp = tot["wall_pc"] / tot["wall_p"] if tot["wall_p"] else 0.0
    walr = tot["wall_gc"] / tot["wall_g"] if tot["wall_g"] else 0.0
    n, found, typed, merged = tot["rooms"]
    dims = sorted(tot["dims"])
    med = dims[len(dims) // 2] if dims else float("nan")
    print(f"{'ALL':<13}{fmt(dp, dr):>13}{fmt(wp, wr):>15}{fmt(walp, walr):>13}  "
          f"{found}/{typed}/{merged} of {n}")
    summary = {"doors": {"P": dp, "R": dr, "F1": df, "tp_fp_fn": tot["doors"]},
               "windows": {"P": wp, "R": wr, "F1": wf, "tp_fp_fn": tot["windows"]},
               "walls": {"P": walp, "R": walr},
               "rooms": {"n": n, "found": found, "typed": typed, "merged": merged,
                         "dim_err_median_pct": med, "dims_checked": len(dims)}}
    print(f"F1 doors {df * 100:.1f}  windows {wf * 100:.1f}  |  room size error median {med:.1f}% "
          f"over {len(dims)} labelled sizes")
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, f"scores_{engine}.json"), "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "plans": report}, f, indent=1, default=str)
    return summary


def main():
    args = sys.argv[1:]
    details = "--details" in args
    plans = None
    if "--plans" in args:
        plans = args[args.index("--plans") + 1].split(",")
    names = [a for a in args if a in engines.ENGINES] or ["vector"]
    labels = [l for l in load_labels(plans) if l.get("status") == "reviewed"]
    for e in names:
        run(e, labels, details)


if __name__ == "__main__":
    main()
