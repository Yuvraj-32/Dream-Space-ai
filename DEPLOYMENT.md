# Deploying DreamSpace AI (free tier)

Two pieces, deployed separately: the **backend** (FastAPI + the ML pipeline)
on an Oracle Cloud "Always Free" VM, and the **frontend** (static Vite build)
on Vercel. This pairing specifically avoids the RAM ceiling that kills this
app on most free web-service tiers — see "Why these platforms" below.

> **Note on platform choice:** this section originally recommended Hugging
> Face Spaces, whose free tier turned out to have changed — Docker/Gradio
> Spaces now require a PRO subscription; only static (no backend) Spaces
> stay free. Free-tier terms shift over time on every platform below, so
> treat the specifics here as a starting point and check the platform's own
> current pricing page before investing setup time.

This is a **demo/prototype deployment**: no auth, no persistence, no upload
limits, CORS wide open (`allow_origins=["*"]`). That's a deliberate choice
for showing the project to people, not a production posture — see
`DreamSpace_AI_Project_Documentation.docx` for what a hardened deployment
would additionally need.

## 1. Backend — Oracle Cloud Always Free VM

Oracle's "Always Free" tier (not a trial — genuinely free with no time
limit) includes an Ampere A1 (ARM) compute allowance of up to 4 OCPUs / 24GB
RAM, which comfortably covers this stack's ~1–2GB usage. The tradeoff versus
a PaaS is that you're managing a real server: installing Docker yourself,
and setting up HTTPS yourself (browsers block a HTTPS frontend from calling
a plain-HTTP backend, so this is required, not optional — covered below).

### 1a. Create the VM

1. Sign up at [oracle.com/cloud/free](https://www.oracle.com/cloud/free/).
   Requires a card for identity verification, but Always Free resources are
   never charged. Pick your home region carefully — it's hard to change
   later, and Ampere A1 capacity availability varies by region.
2. Console → **Compute → Instances → Create Instance**.
3. **Image:** Canonical Ubuntu (a recent LTS).
   **Shape:** Ampere → `VM.Standard.A1.Flex` → 2 OCPUs / 12GB RAM is plenty
   (well within the 4 OCPU / 24GB free allowance).
4. Add your SSH public key (generate one locally first if you don't have
   one: `ssh-keygen -t ed25519`).
5. Leave networking on the default VCN with a public IP assigned. **Create.**
   - If you get an "Out of host capacity" error, this is a well-known,
     common Always-Free-tier issue in busy regions — it's not something you
     did wrong. Retry, try a different Availability Domain, or try again
     later.
6. Note the instance's **public IP**.

### 1b. Open the firewall (two layers — both are required)

Oracle instances are behind two independent firewalls; opening only one is
the most common reason people can't reach their VM.

1. **Cloud-level:** Console → **Networking → Virtual Cloud Networks** →
   your VCN → **Security Lists** → default list → **Add Ingress Rules**:
   source `0.0.0.0/0`, TCP, ports `80` and `443`.
2. **OS-level** (SSH in first — see 1c): Ubuntu images on OCI ship with
   `iptables` pre-configured to drop unlisted inbound traffic:
   ```bash
   sudo iptables -I INPUT -p tcp --dport 80 -j ACCEPT
   sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
   sudo netfilter-persistent save
   ```

### 1c. Set up the server

```bash
ssh ubuntu@<your-vm-public-ip>

sudo apt-get update
sudo apt-get install -y docker.io git caddy
sudo systemctl enable --now docker
sudo usermod -aG docker $USER && newgrp docker

git clone https://github.com/Yuvraj-32/Dream-Space-ai.git
cd Dream-Space-ai/backend
```

### 1d. Build and run the backend

```bash
docker build -t dreamspace-backend .   # 10–20 min: torch, CubiCasa5k clone,
                                        # 209MB weights, EasyOCR pre-warm.
                                        # Run in the foreground so you see
                                        # any failure immediately.

# Bind to localhost only — Caddy (not the container) faces the internet.
docker run -d --name dreamspace --restart unless-stopped \
  -p 127.0.0.1:8001:7860 dreamspace-backend
```

### 1e. Get free HTTPS (required — see note below)

No domain needed: [sslip.io](https://sslip.io) is a free DNS service that
resolves `<ip-with-dashes>.sslip.io` to that IP automatically. Caddy uses it
to get a real Let's Encrypt certificate with zero manual cert management.

```bash
# Replace dots with dashes in your VM's IP, e.g. 123.45.67.89 → 123-45-67-89
echo "123-45-67-89.sslip.io {
    reverse_proxy localhost:8001
}" | sudo tee /etc/caddy/Caddyfile

sudo systemctl restart caddy
```

Verify: `curl https://123-45-67-89.sslip.io/` should return
`{"status":"ok","service":"DreamSpace AI",...}`. That URL (with your actual
IP) is your backend URL — use it as `VITE_API_BASE` in step 2.

> **Why HTTPS is required, not optional:** Vercel always serves the frontend
> over HTTPS. A page served over HTTPS that tries to call a plain `http://`
> backend gets silently blocked by the browser as "mixed content" — it'll
> look like the app is broken with no obvious error. Caddy here solves that
> in about 5 lines of config.

## 2. Frontend — Vercel

1. Create a free account at [vercel.com](https://vercel.com), sign in with
   GitHub, **Add New Project** → import this repo.
2. Set:
   - **Root Directory:** `frontend`
   - **Framework Preset:** Vite (auto-detected)
3. Add an environment variable before deploying:
   - `VITE_API_BASE` = your backend URL from step 1e (no trailing slash)
4. Deploy. Vercel gives you a `https://<project>.vercel.app` URL — that's
   your shareable link.

To change the backend URL later: Project → Settings → Environment Variables
→ edit `VITE_API_BASE` → **Redeploy** (env vars are baked in at build time
for a Vite app, so editing the value alone doesn't take effect without a
rebuild).

## Why these platforms

The backend loads PyTorch + OpenCV + EasyOCR + the CubiCasa5k model
simultaneously, which typically needs 1–2GB+ of RAM during inference. Most
"free" PaaS web-service tiers (Render, Fly.io's free allowance, etc.) cap
out around 256–512MB, which this stack will likely exceed and get
OOM-killed on. An Oracle Always Free Ampere A1 VM sidesteps that entirely —
real RAM headroom, and no cold starts either, since it's an always-on server
rather than a scale-to-zero platform.

Vercel for the frontend has no real tradeoff either way; any static host
(Netlify, Cloudflare Pages, GitHub Pages) works identically for a Vite build.

## Verifying the deploy

1. Open the Vercel URL, upload one of the sample floor plans from the repo
   root (e.g. `3br_cad.jpg` or `house-floor-plan-768x576.webp`).
2. Detection takes ~27–60s (the app's normal CPU inference time — see
   `README.md`; this is not a bug). No cold-start penalty on this setup
   since the VM is always on.
3. If detection fails immediately: open browser devtools → Network tab.
   - Requests going to `localhost:8001` instead of your VM's URL means
     `VITE_API_BASE` wasn't set before the Vercel build ran (rebuild after
     setting it).
   - A blocked/failed request to the right URL over `https://` usually means
     step 1e (Caddy/HTTPS) isn't done yet, or the Caddyfile hostname doesn't
     match the URL you're calling.

## Known limitations of this deployment (by design, not oversight)

| Limitation | Why it's fine for a demo | What production would need |
|---|---|---|
| No persistence | Uploads/results live only for the browser session | A real database + object storage |
| No auth | Anyone with the link can use it | Login + rate limiting |
| CORS wide open | Simplifies the demo setup | Restrict to your frontend's exact domain |
| No upload size limit | Sample plans are all small | A size cap, to control compute cost |
| Manual server ops | Fine for a single demo VM | Managed hosting / auto-scaling |

I have not built/run `backend/Dockerfile` end-to-end in this environment
(no Docker available here) — each step inside it (pip installs, the
CubiCasa5k clone, the exact weights URL) was individually verified working
during local setup, but the full image build itself gets its first real
test in step 1d above. If it fails, the build output printed to your
terminal will show exactly which step broke — send it here and I'll fix it.
