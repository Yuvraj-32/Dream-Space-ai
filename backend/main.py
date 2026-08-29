from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import shutil, os, uuid

app = FastAPI(title="DreamSpace AI Backend", version="0.3.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp"}


def safe_filename(original: str) -> str:
    """UUID-based filename — avoids spaces and special chars causing URL issues."""
    ext = os.path.splitext(original)[-1].lower()
    if ext not in ALLOWED_EXTS:
        ext = ".jpg"
    return f"{uuid.uuid4().hex}{ext}"


def run_detection(image_path: str, engine: str = "classical", measure: bool = False) -> dict:
    """Dispatch to the requested detection engine.

    engine:
      "classical" — the OpenCV pipeline (default; zero heavy deps).
      "ml"        — the CubiCasa5k model; falls back to classical if torch or
                    the weights are unavailable, or on any inference error.
      "auto"      — try ml, fall back to classical.
    measure:
      When true, read the plan's printed dimension labels (OCR), calibrate a
      real-world scale, and annotate walls with length_ft and rooms with
      labeled/computed dimensions. Adds latency; degrades gracefully if OCR
      is unavailable. The returned JSON schema is otherwise identical across
      engines, so the frontend and 3D stages are engine-agnostic.
    """
    from detector import detect_floor_plan

    if engine in ("ml", "auto"):
        try:
            from ml_detector import detect_floor_plan_ml
            result = detect_floor_plan_ml(image_path)
        except Exception as exc:
            result = detect_floor_plan(image_path)
            if engine == "ml":
                result.setdefault("stats", {})["ml_fallback"] = str(exc)
    else:
        result = detect_floor_plan(image_path)

    if measure:
        try:
            from measurements import measure_floor_plan
            result = measure_floor_plan(result, image_path)
        except Exception as exc:
            result.setdefault("stats", {})["measure_error"] = str(exc)

    _ensure_scale(result)
    return result


def _ensure_scale(result: dict) -> None:
    """Guarantee a physically-grounded metres-per-pixel where one is derivable.

    The 3D stage sizes the whole world from this. Printed dimension labels are
    the trustworthy source, but they need `measure=true` AND legible text; when
    they are absent the app used to fall back to a flat 1px=1cm, which is just
    a function of image resolution (the same house came out 15.2 m wide from a
    2732px scan and 2.9 m wide from a 447px one). Detected door widths give a
    real-world anchor instead, so `scale_source` records which one was used and
    callers can present an estimate differently from a measurement.
    """
    stats = result.setdefault("stats", {})
    if stats.get("scale_ft_per_px"):
        stats["scale_source"] = "dimension_labels"
        return

    stats.setdefault("scale_ft_per_px", None)
    stats["scale_source"] = None
    try:
        from measurements import apply_scale, estimate_scale_from_doors
        ft_per_px = estimate_scale_from_doors(result)
    except Exception as exc:
        stats["scale_estimate_error"] = str(exc)
        return

    if ft_per_px:
        apply_scale(result, ft_per_px)
        stats["scale_ft_per_px"] = round(ft_per_px, 5)
        stats["scale_source"] = "door_width"


@app.get("/")
def health_check():
    return {"status": "ok", "service": "DreamSpace AI", "version": "0.4.0"}


@app.post("/upload")
async def upload_floor_plan(file: UploadFile = File(...)):
    """Accept a floor plan image, save with a safe UUID filename."""
    original_name = file.filename or "upload.jpg"
    ext = os.path.splitext(original_name)[-1].lower()
    if ext not in ALLOWED_EXTS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported extension '{ext}'. Use JPEG, PNG, BMP, TIFF, or WebP."},
        )

    filename = safe_filename(original_name)
    save_path = os.path.join(UPLOAD_DIR, filename)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    return {
        "message": "Uploaded. Call /detect/{filename} to run wall detection.",
        "filename": filename,
        "original_name": original_name,
        "content_type": file.content_type,
        "size_bytes": os.path.getsize(save_path),
        "status": "uploaded",
    }


@app.post("/detect/{filename}")
async def detect_walls(filename: str, engine: str = "classical", measure: bool = False):
    """Run the detection pipeline on an uploaded image.

    Query params:
      `engine`: "classical" (default), "ml", or "auto".
      `measure`: when true, add real-world dimensions from the plan's labels.
    """
    image_path = os.path.join(UPLOAD_DIR, filename)
    if not os.path.exists(image_path):
        raise HTTPException(
            status_code=404,
            detail=f"File '{filename}' not found. Upload it first via POST /upload.",
        )
    try:
        return run_detection(image_path, engine, measure)
    except ImportError:
        raise HTTPException(status_code=503, detail="OpenCV not installed.")
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/upload-and-detect")
async def upload_and_detect(file: UploadFile = File(...), engine: str = "classical",
                            measure: bool = False):
    """Single round-trip: upload + detect. Query params `engine`/`measure` as above."""
    original_name = file.filename or "upload.jpg"
    ext = os.path.splitext(original_name)[-1].lower()
    if ext not in ALLOWED_EXTS:
        return JSONResponse(
            status_code=400,
            content={"error": f"Unsupported extension '{ext}'."},
        )

    filename = safe_filename(original_name)
    save_path = os.path.join(UPLOAD_DIR, filename)

    with open(save_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    upload_info = {
        "filename": filename,
        "original_name": original_name,
        "content_type": file.content_type,
        "size_bytes": os.path.getsize(save_path),
    }

    try:
        detection = run_detection(save_path, engine, measure)
        return {"upload": upload_info, "detection": detection}
    except ImportError:
        return {"upload": upload_info, "detection": None, "warning": "OpenCV not installed."}
    except Exception as exc:
        return {"upload": upload_info, "detection": None, "error": str(exc)}
