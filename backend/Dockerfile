# DreamSpace AI backend — CPU-only inference (no GPU needed).
#
# Builds a self-contained image: base deps, the ML engine (torch CPU +
# CubiCasa5k model code + pretrained weights), and a pre-warmed EasyOCR
# model cache, so the container never depends on reaching Google Drive /
# GitHub / the EasyOCR CDN again after build time.
#
# Designed for Hugging Face Spaces (Docker SDK) but portable to any
# container host — see ../DEPLOYMENT.md.

FROM python:3.11-slim

# opencv-python-headless still needs a couple of runtime libs even without
# GUI support; git is needed to clone the CubiCasa5k model repo.
RUN apt-get update && apt-get install -y --no-install-recommends \
    git libglib2.0-0 libsm6 libxext6 libxrender1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Python deps (two layers, so an app-code change doesn't reinstall torch) ──
COPY requirements.txt requirements-ml.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r requirements-ml.txt \
        --index-url https://download.pytorch.org/whl/cpu \
        --extra-index-url https://pypi.org/simple

# ── ML engine assets (gitignored in the repo; fetched at build time) ──
RUN git clone --depth 1 https://github.com/CubiCasa/CubiCasa5k.git ml/CubiCasa5k
RUN mkdir -p ml/weights && python -m gdown \
    "https://drive.google.com/uc?id=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK" \
    -O ml/weights/model_best_val_loss_var.pkl

# Pre-warm EasyOCR's detection/recognition models into the image so the
# first real request doesn't pay a cold download — and so the container
# still works if EasyOCR's model CDN is ever unreachable at runtime.
RUN python -c "import easyocr; easyocr.Reader(['en'], gpu=False)"

# ── App code ──
COPY . .

# Hugging Face Spaces (Docker SDK) expects the app on port 7860; most other
# hosts inject $PORT. Shell form so the ${PORT:-7860} default expands.
EXPOSE 7860
CMD uvicorn main:app --host 0.0.0.0 --port ${PORT:-7860}
