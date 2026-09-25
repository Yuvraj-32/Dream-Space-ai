"""DWG -> DXF conversion via LibreDWG's free `dwg2dxf` tool, with a per-file cache.

DWG is a closed binary format; LibreDWG (GPLv3, free) is run as a separate
program, so nothing here links against it. DXF input needs no conversion.
"""
import hashlib
import os
import re
import shutil
import subprocess
import tempfile
import time

CAD_EXTS = {".dwg", ".dxf"}
MAX_CAD_BYTES = 50 * 1024 * 1024
CONVERT_TIMEOUT_S = int(os.environ.get("CAD_CONVERT_TIMEOUT_S", "120"))

# Where Phase 0 installed it on the dev machine; env var / PATH take priority.
_DEFAULT_WIN_PATH = r"C:\tools\libredwg\dwg2dxf.exe"


class CadError(RuntimeError):
    """Base error; `status` is the HTTP status the API should return."""
    status = 422


class ConverterNotInstalled(CadError):
    status = 503


class ConversionFailed(CadError):
    status = 422


class FileTooLarge(CadError):
    status = 413


def find_dwg2dxf():
    env = os.environ.get("LIBREDWG_DWG2DXF")
    if env and os.path.isfile(env):
        return env
    on_path = shutil.which("dwg2dxf")
    if on_path:
        return on_path
    if os.name == "nt" and os.path.isfile(_DEFAULT_WIN_PATH):
        return _DEFAULT_WIN_PATH
    return None


def converter_info():
    exe = find_dwg2dxf()
    if not exe:
        return {"dwg2dxf": False, "path": None, "version": None}
    try:
        out = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=10)
        m = re.search(r"(\d+(?:\.\d+)+)", (out.stdout or "") + (out.stderr or ""))
        version = m.group(1) if m else None
    except (OSError, subprocess.TimeoutExpired):
        version = None
    return {"dwg2dxf": True, "path": exe, "version": version}


def file_session_id(path):
    """Content hash (first 16 hex chars of SHA-256) — identical uploads share a cache entry."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def dwg_version(path):
    with open(path, "rb") as f:
        return f.read(6).decode("ascii", "replace")


def ensure_dxf(src_path, session_dir):
    """Return (dxf_path, info). DWG files are converted once into
    `session_dir/plan.dxf` and reused on later calls."""
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in CAD_EXTS:
        raise CadError(f"Not a CAD file: '{ext}'")
    size = os.path.getsize(src_path)
    if size > MAX_CAD_BYTES:
        raise FileTooLarge(
            f"CAD file is {size / 1048576:.1f} MB; the limit is {MAX_CAD_BYTES // 1048576} MB."
        )

    if ext == ".dxf":
        return src_path, {"format": "dxf", "version": None, "converter": None, "convert_seconds": 0.0}

    info = {"format": "dwg", "version": dwg_version(src_path), "converter": "libredwg"}
    cached = os.path.join(session_dir, "plan.dxf")
    if os.path.isfile(cached) and os.path.getsize(cached) > 0:
        info.update(convert_seconds=0.0, cached=True)
        return cached, info

    exe = find_dwg2dxf()
    if not exe:
        raise ConverterNotInstalled(
            "Reading .dwg files needs LibreDWG's free dwg2dxf tool, which isn't installed "
            "on this server. Install it (see 'cad update folder' README) and set "
            "LIBREDWG_DWG2DXF, or upload the drawing as .dxf instead "
            "(AutoCAD: File > Save As > DXF)."
        )

    os.makedirs(session_dir, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dwg2dxf_") as tmp:
        out = os.path.join(tmp, "plan.dxf")
        t0 = time.time()
        try:
            proc = subprocess.run([exe, "-y", "-o", out, src_path],
                                  capture_output=True, text=True, errors="replace",
                                  timeout=CONVERT_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            raise ConversionFailed(
                f"DWG conversion took longer than {CONVERT_TIMEOUT_S}s. Try saving the "
                "drawing as .dxf, or remove unused layouts/blocks first."
            )
        info["convert_seconds"] = round(time.time() - t0, 2)
        log = (proc.stderr or "") + (proc.stdout or "")
        info["converter_warnings"] = sum(1 for line in log.splitlines() if "WARN" in line.upper())
        if proc.returncode != 0 or not os.path.isfile(out) or os.path.getsize(out) == 0:
            tail = " | ".join(log.strip().splitlines()[-3:])
            raise ConversionFailed(
                f"LibreDWG could not convert this DWG (version {info['version']}). "
                f"Try saving it as .dxf from AutoCAD. Details: {tail}"
            )
        shutil.move(out, cached)
    info["cached"] = False
    return cached, info
