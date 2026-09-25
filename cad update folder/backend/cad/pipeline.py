"""CAD orchestration. Phase 1: `inspect_file` (no wall generation yet).

inspect = convert (DWG only) → read DXF → units → flatten → layer roles →
drawing clusters → thumbnails. The result is cached per file content hash in
`<cache_root>/<session_id>/inspect.json`, so re-opening the same drawing is instant.
"""
import json
import os
import time

from .clusters import find_clusters
from .converter import ConversionFailed, ensure_dxf, file_session_id
from .layers import analyze_layers
from .loader import flatten, header_units, load_doc
from .render import render_cluster
from .units import resolve_units

INSPECT_VERSION = 3


def session_dir(cache_root, session_id):
    return os.path.join(cache_root, session_id)


def inspect_file(src_path, cache_root, use_cache=True):
    sid = file_session_id(src_path)
    sdir = session_dir(cache_root, sid)
    os.makedirs(sdir, exist_ok=True)
    cache_json = os.path.join(sdir, "inspect.json")
    if use_cache and os.path.isfile(cache_json):
        with open(cache_json, encoding="utf-8") as f:
            cached = json.load(f)
        if cached.get("inspect_version") == INSPECT_VERSION:
            cached["cached"] = True
            return cached

    timings = {}
    t = time.time()
    dxf_path, source = ensure_dxf(src_path, sdir)
    timings["convert"] = round(time.time() - t, 2)

    t = time.time()
    doc, audit = load_doc(dxf_path)
    timings["read"] = round(time.time() - t, 2)

    t = time.time()
    code, header_name, header_mpu = header_units(doc)
    flat_mpu = header_mpu or 0.001
    records, flat_stats = flatten(doc, flat_mpu)
    if not records:
        # Phase 0: a 35 MB AutoCAD 2010 file "converted" successfully into an
        # empty drawing — LibreDWG can silently drop everything.
        raise ConversionFailed(
            "The drawing came out empty after reading"
            + (" — the DWG converter couldn't read this file's content (a known "
               "limitation for some AutoCAD 2010+ files)." if source["format"] == "dwg" else ".")
            + " Save it as .dxf from AutoCAD and upload that instead."
        )
    units = resolve_units(records, header_name)
    units["insunits"] = code
    mpu = units["metres_per_unit"]
    if not 0.5 <= mpu / flat_mpu <= 2.0:
        # Curve-flattening tolerance was based on the wrong unit; redo it.
        records, flat_stats = flatten(doc, mpu)
    timings["flatten"] = round(time.time() - t, 2)

    t = time.time()
    layers = analyze_layers(doc, records, mpu)
    roles = {l["name"]: l["suggested_role"] for l in layers}
    timings["layers"] = round(time.time() - t, 2)

    t = time.time()
    clusters, cluster_stats = find_clusters(records, mpu, roles)
    timings["clusters"] = round(time.time() - t, 2)

    t = time.time()
    thumbs_dir = os.path.join(sdir, "thumbs")
    os.makedirs(thumbs_dir, exist_ok=True)
    for c in clusters:
        w, h = render_cluster(records, c["_records"], c["bbox"], roles,
                              os.path.join(thumbs_dir, f"{c['id']}.png"))
        c["thumbnail_size"] = [w, h]
    timings["thumbnails"] = round(time.time() - t, 2)

    result = {
        "inspect_version": INSPECT_VERSION,
        "session_id": sid,
        "source": {**source, **audit},
        "units": units,
        "clusters": [{k: v for k, v in c.items() if not k.startswith("_")} for c in clusters],
        "layers": layers,
        "stats": {**flat_stats, **cluster_stats, "timings_s": timings},
        "warnings": _warnings(source, flat_stats, clusters, layers, units),
        "cached": False,
    }
    with open(cache_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)
    return result


def _warnings(source, flat_stats, clusters, layers, units):
    out = []
    if flat_stats.get("truncated"):
        out.append("This drawing is very large; only part of it was read. "
                   "Consider saving just the floor plan to a separate file.")
    if not clusters:
        out.append("No drawings were found in this file's model space.")
    elif not any(c["suggested"] for c in clusters):
        out.append("Nothing in this file looks clearly like a floor plan (no drawing has both wall "
                   "lines and room names or door swings). If one of the drawings is your plan, pick it manually.")
    for c in clusters:
        if c.get("walls_missing"):
            out.append(f"Drawing {c['id']} has room names ({', '.join(c['room_labels'][:3])}…) but no walls — "
                       "they were likely lost when converting the DWG. If that's your floor plan, "
                       "save it as .dxf from AutoCAD and upload that instead.")
    if not any(l["suggested_role"] == "wall" for l in layers):
        out.append("No layer was recognised as walls — please mark the wall layer(s) in the review step.")
    if units["confidence"] == "guess":
        out.append(f"The drawing has no units set; its geometry suggests '{units['name']}' — please confirm.")
    elif units["confidence"] == "corrected":
        out.append(f"The drawing says its units are '{units['header']}', but its walls and doors only make "
                   f"sense in '{units['name']}', so '{units['name']}' is used — please confirm.")
    if source.get("converter_warnings"):
        out.append(f"The DWG converter reported {source['converter_warnings']} minor warnings "
                   "(usually harmless; check the preview looks complete).")
    return out
