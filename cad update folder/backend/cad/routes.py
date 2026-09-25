"""FastAPI routes for CAD input, mounted by backend/main.py under /cad.

  GET  /cad/health                         is LibreDWG's dwg2dxf available?
  POST /cad/inspect/{filename}             drawings, layers (suggested roles), units
  GET  /cad/thumb/{session}/{cluster}.png  per-drawing thumbnail
  POST /cad/detect/{filename}              walls/openings/rooms for the chosen drawing
  GET  /cad/preview/{session}/{file}.png   editor background, same pixel space as /detect
"""
import os
import re
from typing import Dict, Optional

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .converter import CadError, converter_info
from .detect import detect_file
from .pipeline import inspect_file, session_dir

_UPLOAD_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(dwg|dxf)$")
_SESSION_RE = re.compile(r"^[0-9a-f]{16}$")
_CLUSTER_RE = re.compile(r"^c\d{1,2}$")
_PREVIEW_RE = re.compile(r"^preview_c\d{1,2}_[0-9a-f]{10}\.png$")


class DetectRequest(BaseModel):
    cluster_id: Optional[str] = None           # default: the suggested floor plan
    layer_roles: Optional[Dict[str, str]] = None  # overrides, e.g. {"0": "ignore", "A-WALL": "wall"}
    units: Optional[str] = None                # "mm" | "cm" | "m" | "in" | "ft"


def create_cad_router(upload_dir, cache_root):
    router = APIRouter(prefix="/cad", tags=["cad"])

    def upload_path(filename):
        if not _UPLOAD_NAME_RE.match(filename):
            raise HTTPException(400, "Expected an uploaded CAD filename (from POST /upload).")
        path = os.path.join(upload_dir, filename)
        if not os.path.isfile(path):
            raise HTTPException(404, f"File '{filename}' not found. Upload it first via POST /upload.")
        return path

    @router.get("/health")
    def health():
        return converter_info()

    @router.post("/inspect/{filename}")
    def inspect(filename: str, refresh: bool = False):
        """Convert/read an uploaded .dwg/.dxf and return its drawings (clusters),
        layers with suggested roles, and units — for the review step."""
        path = upload_path(filename)
        try:
            result = inspect_file(path, cache_root, use_cache=not refresh)
        except CadError as exc:
            raise HTTPException(exc.status, str(exc))
        sid = result["session_id"]
        for c in result["clusters"]:
            c["thumbnail_url"] = f"/cad/thumb/{sid}/{c['id']}.png"
        return result

    @router.post("/detect/{filename}")
    def detect(filename: str, body: Optional[DetectRequest] = None):
        """Walls, doors/windows and rooms for one drawing, in the same JSON schema
        as /detect for images, plus `preview_url` (the editor's background image)."""
        path = upload_path(filename)
        body = body or DetectRequest()
        if body.cluster_id is not None and not _CLUSTER_RE.match(body.cluster_id):
            raise HTTPException(400, "Bad cluster_id.")
        try:
            result = detect_file(path, cache_root, body.cluster_id, body.layer_roles, body.units)
        except CadError as exc:
            raise HTTPException(exc.status, str(exc))
        result["preview_url"] = f"/cad/preview/{result['session_id']}/{result.pop('preview_file')}"
        return result

    @router.get("/thumb/{session_id}/{cluster_file}")
    def thumbnail(session_id: str, cluster_file: str):
        cluster_id, ext = os.path.splitext(cluster_file)
        if not _SESSION_RE.match(session_id) or not _CLUSTER_RE.match(cluster_id) or ext != ".png":
            raise HTTPException(400, "Bad thumbnail path.")
        path = os.path.join(session_dir(cache_root, session_id), "thumbs", f"{cluster_id}.png")
        if not os.path.isfile(path):
            raise HTTPException(404, "Thumbnail not found — run /cad/inspect first.")
        return FileResponse(path, media_type="image/png")

    @router.get("/preview/{session_id}/{preview_file}")
    def preview(session_id: str, preview_file: str):
        if not _SESSION_RE.match(session_id) or not _PREVIEW_RE.match(preview_file):
            raise HTTPException(400, "Bad preview path.")
        path = os.path.join(session_dir(cache_root, session_id), preview_file)
        if not os.path.isfile(path):
            raise HTTPException(404, "Preview not found — run /cad/detect first.")
        return FileResponse(path, media_type="image/png")

    return router
