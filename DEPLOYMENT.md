# Deploying DreamSpace AI (free tier)

Two pieces, deployed separately: the **backend** (FastAPI + the ML pipeline)
on Hugging Face Spaces, and the **frontend** (static Vite build) on Vercel.
Both are free, and this pairing specifically avoids the RAM ceiling that
kills this app on most free web-service tiers — see "Why these platforms"
below.

This is a **demo/prototype deployment**: no auth, no persistence, no upload
limits, CORS wide open (`allow_origins=["*"]`). That's a deliberate choice
for showing the project to people, not a production posture — see
`DreamSpace_AI_Project_Documentation.docx` for what a hardened deployment
would additionally need.

## 1. Backend — Hugging Face Spaces

1. Create a free account at [huggingface.co](https://huggingface.co) — no
   credit card required.
2. **New Space** → any name → SDK: **Docker** → Hardware: **CPU basic (free)**
   → Visibility: your choice.
3. Push this repo's `backend/` folder as the Space's contents. Simplest way,
   from your machine:
   ```bash
   git clone https://huggingface.co/spaces/<your-username>/<space-name>
   cp -r backend/* backend/.dockerignore backend/Dockerfile <space-name>/
   cd <space-name>
   git add . && git commit -m "Deploy DreamSpace backend" && git push
   ```
   (Or connect the Space to this GitHub repo directly from the HF UI, with
   `backend/` as the subdirectory — see the Space's Settings → Repository.)
4. HF Spaces builds `backend/Dockerfile` automatically. **First build takes
   10–20 minutes** — it's installing torch, cloning CubiCasa5k, downloading
   the 209MB model weights, and pre-caching EasyOCR's models. Watch progress
   under the Space's **Logs** tab.
5. Once built, your backend URL is:
   `https://<your-username>-<space-name>.hf.space`
   Confirm it's alive: `curl https://<...>.hf.space/` should return
   `{"status":"ok","service":"DreamSpace AI",...}`.

**Cold starts:** a free Space sleeps after inactivity and takes ~30–60s to
wake on the next request, on top of this app's own ~30s model-load time on
first inference. The *second* request onward is normal speed (27–60s per
detection, per the app's own timing — this is CPU inference, not a bug).

## 2. Frontend — Vercel

1. Create a free account at [vercel.com](https://vercel.com), sign in with
   GitHub, **Add New Project** → import this repo.
2. Set:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite (auto-detected)
3. Add an environment variable before deploying:
   - `VITE_API_BASE` = your HF Spaces URL from step 1.5 (no trailing slash)
4. Deploy. Vercel gives you a `https://<project>.vercel.app` URL — that's
   your shareable link.

To change the backend URL later: Project → Settings → Environment Variables
→ edit `VITE_API_BASE` → **Redeploy** (env vars are baked in at build time
for a Vite app, so editing the value alone doesn't take effect without a
rebuild).

## Why these platforms

The backend loads PyTorch + OpenCV + EasyOCR + the CubiCasa5k model
simultaneously, which typically needs 1–2GB+ of RAM during inference. Most
"free" web-service tiers (Render, Fly.io's free allowance, etc.) cap out
around 256–512MB, which this stack will likely exceed and get OOM-killed on.
Hugging Face Spaces' free CPU tier gives **16GB RAM**, and is literally built
for hosting exactly this kind of ML demo — no credit card, no surprise bill.

Vercel for the frontend has no real tradeoff either way; any static host
(Netlify, Cloudflare Pages, GitHub Pages) works identically for a Vite build.

## Verifying the deploy

1. Open the Vercel URL, upload one of the sample floor plans from the repo
   root (e.g. `3br_cad.jpg` or `house-floor-plan-768x576.webp`).
2. First detection after a cold Space will be slow (wake + model load +
   inference, ~60–90s total). Subsequent ones are ~27–60s (the app's normal
   CPU inference time — see `README.md`).
3. If detection fails immediately: open browser devtools → Network tab,
   confirm requests are going to your HF Spaces URL, not `localhost:8001`
   (that would mean `VITE_API_BASE` wasn't set before the Vercel build ran).

## Known limitations of this deployment (by design, not oversight)

| Limitation | Why it's fine for a demo | What production would need |
|---|---|---|
| No persistence | Uploads/results live only for the browser session | A real database + object storage |
| No auth | Anyone with the link can use it | Login + rate limiting |
| CORS wide open | Simplifies the demo setup | Restrict to your frontend's exact domain |
| No upload size limit | Sample plans are all small | A size cap, to control compute cost |
| Free-tier cold starts | Acceptable for occasional demo use | A paid always-on tier |

I have not built/run `backend/Dockerfile` end-to-end in this environment
(no Docker available here) — each step inside it (pip installs, the
CubiCasa5k clone, the exact weights URL) was individually verified working
during local setup, but the full image build itself will get its first real
test on Hugging Face Spaces' own build. If it fails, the Space's **Logs**
tab will show exactly which step broke.
