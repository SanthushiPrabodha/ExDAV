# Deploying Ex-DAV on free hosting

The project has **two deployable pieces**:

| Piece | Folder | What it needs | Good free hosts |
|-------|--------|---------------|-----------------|
| Backend API | `backend/` + `src/` | Python 3.11, `tesseract-ocr` system package, FastAPI/uvicorn | **Render** (free web service), Railway (trial credit), Fly.io, Google Cloud Run |
| Frontend SPA | `frontend/` | Node 18+, `npm run build` static output | **Vercel**, Netlify, Render static site, GitHub Pages |

> The Streamlit app (`streamlit_app.py`), the CLI (`run_pipeline.py`), the `src/vision` training code and everything else is **not** deployed — the web app only exposes `POST /analyze` via FastAPI.

---

## Files added for deployment

```
Procfile                 # Universal "web:" start command
requirements-deploy.txt  # Slim backend deps (no TF / Streamlit / SHAP)
apt.txt                  # System packages for Render (tesseract)
render.yaml              # One-click Render Blueprint
Dockerfile               # Container for Railway / Fly / Cloud Run
.dockerignore
frontend/vercel.json     # Vercel SPA config
frontend/netlify.toml    # Netlify SPA config
frontend/.env.example    # REACT_APP_BACKEND_URL template
```

`frontend/src/App.js` now reads `process.env.REACT_APP_BACKEND_URL` so the
same build can target local, Render, Railway, or any other backend URL.

Runtime start command (all platforms):

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

---

## Option A — Render (backend) + Vercel (frontend) — recommended free combo

### 1. Push the repo to GitHub

Render and Vercel both deploy from GitHub. Make sure `venv/`, `exdav_env/`,
`node_modules/`, `outputs/`, `backend/uploads/` are in `.gitignore` before
you push (the existing `.gitignore` at the repo root should cover these).

### 2. Backend on Render

1. Go to <https://dashboard.render.com> → **New +** → **Blueprint**.
2. Select this repo — Render detects `render.yaml` and proposes a
   `exdav-backend` web service on the **Free** plan.
3. Click **Apply**. Render will:
   - install `tesseract-ocr` from `apt.txt`,
   - run `pip install -r requirements-deploy.txt`,
   - start `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
4. Once the service is live, note its URL, e.g.
   `https://exdav-backend.onrender.com`. Hit `/` in a browser — you should
   see `{"message":"Ex-DAV Backend Running"}`.

> Free web services on Render **sleep after 15 minutes of inactivity** and
> cold-start in ~30–60 s. The first request after idle will be slow; that
> is normal.

### 3. Frontend on Vercel

1. Go to <https://vercel.com/new> and import the same GitHub repo.
2. When Vercel asks for the **Root Directory**, pick `frontend`.
3. Framework preset: **Create React App** (auto-detected via
   `vercel.json`). Build command `npm run build`, output `build`.
4. Under **Environment Variables**, add:
   - `REACT_APP_BACKEND_URL = https://exdav-backend.onrender.com`
     (no trailing slash — the frontend appends `/analyze` itself).
5. Deploy. Vercel gives you a URL like
   `https://ex-dav.vercel.app`. Open it and upload a package image — the
   browser calls the Render backend directly (CORS is already set to
   `*` in `backend/main.py`).

### 4. (Optional) Lock down CORS

Once you know the frontend origin, tighten `backend/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://ex-dav.vercel.app"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## Option B — Railway (backend) + Vercel/Netlify (frontend)

Railway gives each new account a small monthly free credit and runs
containers directly, so it uses the `Dockerfile` instead of `apt.txt`.

1. <https://railway.app> → **New Project** → **Deploy from GitHub repo**.
2. Railway auto-detects the `Dockerfile`. Set these variables:
   - `PORT` — Railway injects this automatically, nothing to set.
   - `TESSERACT_CMD=/usr/bin/tesseract` (already baked into the image).
3. Click **Deploy**. Copy the generated public domain, e.g.
   `https://exdav-backend.up.railway.app`.
4. Deploy the frontend on Vercel or Netlify as in Option A, setting
   `REACT_APP_BACKEND_URL` to the Railway URL.

## Option C — Fly.io (backend)

Fly's free-ish tier also works with the provided `Dockerfile`:

```bash
# Install flyctl once: https://fly.io/docs/hands-on/install-flyctl/
fly launch --no-deploy          # accept Dockerfile, pick a region
fly deploy
fly status                      # note the hostname (*.fly.dev)
```

Then point the frontend at the `*.fly.dev` URL via
`REACT_APP_BACKEND_URL`.

## Option D — Netlify for the frontend

If you prefer Netlify over Vercel:

1. <https://app.netlify.com/start> → pick the repo.
2. `netlify.toml` at `frontend/netlify.toml` configures the base, build
   command, publish dir, and SPA fallback.
3. In the Netlify UI, set **Base directory** to `frontend` and add the
   env var `REACT_APP_BACKEND_URL=https://<your-backend>`.

---

## Run commands cheat-sheet

| Where | Command |
|-------|---------|
| Local backend | `uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload` |
| Local frontend | `cd frontend && npm install && npm start` |
| Local backend (Docker) | `docker build -t exdav-backend . && docker run -p 8000:8000 exdav-backend` |
| Render / Railway / Fly | `uvicorn backend.main:app --host 0.0.0.0 --port $PORT` |
| Production frontend build | `cd frontend && npm run build` (outputs `frontend/build`) |

---

## Free-tier gotchas

- **Cold starts.** Render free services sleep after 15 min idle. Use
  a cron-style ping (e.g. [cron-job.org](https://cron-job.org)) hitting
  `GET /` every 10 minutes if you need them always warm.
- **Memory.** The slim `requirements-deploy.txt` keeps the image small
  enough for 512 MB RAM. Do **not** revert to `requirements.txt` on a
  free plan — TensorFlow alone will OOM the build.
- **Ephemeral disk.** `backend/uploads/` is wiped on every deploy /
  restart. That's fine because the analyse endpoint only needs the
  image long enough to run OCR.
- **Tesseract.** On Render it is installed from `apt.txt`; in Docker it
  is installed in the image; on Fly/Railway the Dockerfile handles it.
  The code picks it up via `shutil.which("tesseract")` with a
  `TESSERACT_CMD` env-var override.
- **CORS.** `backend/main.py` currently allows all origins; tighten it
  to your deployed frontend domain once everything works.
