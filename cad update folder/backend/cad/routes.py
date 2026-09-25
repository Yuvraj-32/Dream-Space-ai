"""FastAPI routes for CAD input, mounted by backend/main.py under /cad."""
import os
import re

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from .converter import CAD_EXTS, CadError, converter_info
from .pipeline import inspect_file, session_dir

_UPLOAD_NAME_RE = re.compile(r"^[0-9a-f]{32}\.(dwg|dxf)$")
_SESSION_RE = re.compile(r"^[0-9a-f]{16}$")
_CLUSTER_RE = re.compile(r"^c\d{1,2}$")


def create_cad_router(upload_dir, cache_root):
    router = APIRouter(prefix="/cad", tags=["cad"])

    @router.get("/health")
    def health():
        return converter_info()

    @router.post("/inspect/{filename}")
    def inspect(filename: str, refresh: bool = False):
        """Convert/read an uploaded .dwg/.dxf and return its drawings (clusters),
        layers with suggested roles, and units — for the review step."""
        if not _UPLOAD_NAME_RE.match(filename):
            raise HTTPException(400, "Expected an uploaded CAD filename (from POST /upload).")
        path = os.path.join(upload_dir, filename)
        if not os.path.isfile(path):
            raise HTTPException(404, f"File '{filename}' not found. Upload it first via POST /upload.")
        try:
            result = inspect_file(path, cache_root, use_cache=not refresh)
        except CadError as exc:
            raise HTTPException(exc.status, str(exc))
        sid = result["session_id"]
        for c in result["clusters"]:
            c["thumbnail_url"] = f"/cad/thumb/{sid}/{c['id']}.png"
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

    return router


def is_cad_filename(name):
    return os.path.splitext(name)[1].lower() in CAD_EXTS
