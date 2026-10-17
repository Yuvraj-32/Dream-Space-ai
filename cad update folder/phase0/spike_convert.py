"""Phase 0 feasibility spike: convert every sample DWG with LibreDWG's
dwg2dxf, load the result with ezdxf, and record what we get.

Usage:  python spike_convert.py
Env:    LIBREDWG_DWG2DXF  (default C:\\tools\\libredwg\\dwg2dxf.exe)
Output: phase0/out/<name>/plan.dxf, thumb.png, report.json
        phase0/out/summary.json
"""
import collections
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(HERE, "out")
DWG2DXF = os.environ.get("LIBREDWG_DWG2DXF", r"C:\tools\libredwg\dwg2dxf.exe")
TIMEOUT_S = 300
MAX_RENDER_ENTITIES = 150_000

_UNITS = {0: "unitless", 1: "in", 2: "ft", 4: "mm", 5: "cm", 6: "m"}


def collect_samples():
    samples = [os.path.join(PROJECT, f) for f in sorted(os.listdir(PROJECT)) if f.lower().endswith(".dwg")]
    for z in (f for f in os.listdir(PROJECT) if f.lower().endswith(".zip")):
        with zipfile.ZipFile(os.path.join(PROJECT, z)) as zf:
            for name in zf.namelist():
                if name.lower().endswith(".dwg"):
                    dest = os.path.join(tempfile.gettempdir(), "phase0_zip", os.path.basename(name))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with zf.open(name) as src, open(dest, "wb") as dst:
                        shutil.copyfileobj(src, dst)
                    samples.append(dest)
    return sorted(samples, key=os.path.getsize)


def convert(dwg, out_dxf):
    t0 = time.time()
    try:
        proc = subprocess.run([DWG2DXF, "-y", "-o", out_dxf, dwg],
                              capture_output=True, text=True, errors="replace", timeout=TIMEOUT_S)
    except subprocess.TimeoutExpired:
        return {"ok": False, "seconds": TIMEOUT_S, "error": "timeout"}
    secs = round(time.time() - t0, 1)
    lines = (proc.stderr or "").splitlines() + (proc.stdout or "").splitlines()
    return {
        "ok": proc.returncode == 0 and os.path.exists(out_dxf) and os.path.getsize(out_dxf) > 0,
        "returncode": proc.returncode,
        "seconds": secs,
        "dxf_mb": round(os.path.getsize(out_dxf) / 1048576, 1) if os.path.exists(out_dxf) else 0,
        "error_lines": sum(1 for l in lines if "ERROR" in l.upper()),
        "warning_lines": sum(1 for l in lines if "WARN" in l.upper()),
        "log_tail": lines[-8:],
    }


def inspect(dxf_path):
    import ezdxf
    from ezdxf import recover

    t0 = time.time()
    doc, auditor = recover.readfile(dxf_path)
    msp = doc.modelspace()
    types = collections.Counter(e.dxftype() for e in msp)
    per_layer = collections.Counter(e.dxf.layer for e in msp if e.dxf.hasattr("layer"))
    texts = []
    for e in msp.query("TEXT MTEXT"):
        try:
            t = e.dxf.text if e.dxftype() == "TEXT" else e.plain_text()
        except Exception:
            continue
        t = " ".join((t or "").split())
        if t and len(t) <= 40:
            texts.append(t)
    blocks = collections.Counter(e.dxf.name for e in msp.query("INSERT"))
    code = int(doc.header.get("$INSUNITS", 0) or 0)
    return doc, {
        "load_seconds": round(time.time() - t0, 1),
        "acadver": doc.header.get("$ACADVER"),
        "insunits": code,
        "units": _UNITS.get(code, f"code {code}"),
        "audit_errors": len(auditor.errors),
        "audit_fixes": len(auditor.fixes),
        "modelspace_entities": sum(types.values()),
        "entity_types": dict(types.most_common(12)),
        "layer_count": len(doc.layers),
        "top_layers": dict(per_layer.most_common(15)),
        "top_blocks": dict(blocks.most_common(10)),
        "text_samples": list(dict.fromkeys(texts))[:25],
    }


def render_thumb(doc, png_path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import RenderContext, Frontend
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    t0 = time.time()
    fig = plt.figure(figsize=(8, 8), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    Frontend(RenderContext(doc), MatplotlibBackend(ax)).draw_layout(doc.modelspace(), finalize=True)
    fig.savefig(png_path, facecolor="#141824")
    plt.close(fig)
    return round(time.time() - t0, 1)


def main():
    if not os.path.isfile(DWG2DXF):
        sys.exit(f"dwg2dxf not found at {DWG2DXF}")
    os.makedirs(OUT, exist_ok=True)
    summary = []
    for dwg in collect_samples():
        name = os.path.splitext(os.path.basename(dwg))[0]
        folder = os.path.join(OUT, name)
        os.makedirs(folder, exist_ok=True)
        with open(dwg, "rb") as f:
            header = f.read(6).decode("ascii", "replace")
        rep = {"file": os.path.basename(dwg), "dwg_version": header,
               "dwg_mb": round(os.path.getsize(dwg) / 1048576, 1)}
        print(f"\n=== {rep['file']} ({header}, {rep['dwg_mb']} MB)", flush=True)

        dxf = os.path.join(folder, "plan.dxf")
        rep["convert"] = convert(dwg, dxf)
        print(f"  convert: ok={rep['convert']['ok']} {rep['convert']['seconds']}s", flush=True)

        if rep["convert"]["ok"]:
            try:
                doc, rep["inspect"] = inspect(dxf)
                print(f"  inspect: {rep['inspect']['modelspace_entities']} entities, "
                      f"units={rep['inspect']['units']}, audit_errors={rep['inspect']['audit_errors']}", flush=True)
                if rep["inspect"]["modelspace_entities"] > MAX_RENDER_ENTITIES:
                    rep["render_skipped"] = f"> {MAX_RENDER_ENTITIES} entities"
                    print(f"  render skipped ({rep['inspect']['modelspace_entities']} entities)", flush=True)
                else:
                    try:
                        rep["render_seconds"] = render_thumb(doc, os.path.join(folder, "thumb.png"))
                        print(f"  render: {rep['render_seconds']}s", flush=True)
                    except Exception as exc:
                        rep["render_error"] = f"{type(exc).__name__}: {exc}"
                        print(f"  render FAILED: {rep['render_error']}", flush=True)
            except Exception as exc:
                rep["inspect_error"] = f"{type(exc).__name__}: {exc}"
                print(f"  inspect FAILED: {rep['inspect_error']}", flush=True)

        with open(os.path.join(folder, "report.json"), "w", encoding="utf-8") as f:
            json.dump(rep, f, indent=2, ensure_ascii=False)
        summary.append(rep)

    with open(os.path.join(OUT, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print("\nDone.")


if __name__ == "__main__":
    main()
