# WindSight: frontend on Vercel, API on Render

This is a deployment guide for the existing React/Vite + FastAPI project. The Vercel site is a static frontend; the Python API must run on a separate persistent service for data imports and saved forecasts to survive restarts.

## A. Confirm GitHub repo

Push the contents of the `windsight/` directory as the repository root (its `frontend/` and `backend/` folders should be visible in GitHub). Check that `.venv`, `node_modules`, `.env`, `backend/data/raw/**/*.json`, and `backend/data/predictions/*.json` are not committed.

## B. Deploy the FastAPI backend to Render first

At https://dashboard.render.com create **New → Web Service**, connect the GitHub repo and select: 

- Root Directory: `backend`
- Language/Runtime: `Python`
- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- Health-check path: `/api/health`
- Environment variable: `PYTHON_VERSION=3.13.5` (only if a compatible runtime version needs pinning; omit otherwise)
- Environment variable: `WINDSIGHT_DATA_DIR=/var/data/windsight` **only when using a disk mounted at `/var/data`**.
- Environment variable: `CORS_ORIGINS=https://YOUR-VERCEL-PROJECT.vercel.app` (set/adjust after deployment).

Create the service, wait for healthy status, and open `https://YOUR-RENDER-SERVICE.onrender.com/api/health`. A successful response has `status: ok`. Save the **backend base URL** without `/api/health`.

**Persistence**: Render web services use ephemeral storage by default. For durable Elexon snapshots and immutable issued predictions, choose a compatible **paid** service and attach a persistent disk at `/var/data`, then set `WINDSIGHT_DATA_DIR=/var/data/windsight` and redeploy. For a no-cost *temporary demo*, omit the disk and the variable; imported data and saved predictions will be lost after service restart/redeploy. Do not claim that demo is production ready.

## C. Deploy frontend on Vercel

Visit https://vercel.com/new, log in, **Add New Project → Import Git repository**. Configure: 

- Root Directory: `frontend`
- Framework Preset: `Vite`
- Build Command: `npm run build`
- Output Directory: `dist`
- Install Command: `npm install`
- **Environment Variables**: `VITE_API_BASE_URL=https://YOUR-RENDER-SERVICE.onrender.com` (replace with your real URL; no `/api` suffix)

Click **Deploy**. Copy the new `https://...vercel.app` URL.

## D. CORS, redeploy, verify

In Render: set `CORS_ORIGINS` to the exact **Vercel** site origin, e.g. `https://your-app.vercel.app`, then redeploy/restart. If you also use preview deployments, allow their specific origins instead of unrestricted `*`.

On the Vercel app:

1. Open browser Developer Tools → Network; inspect `/api/health` directly on Render first, and `/api/status` from the Vercel site.
2. Test **Historical Replay** → Fetch required data → Recalculate; note that source downloads take time.
3. Test **History** range and CSV export.
4. Test **Live Prediction** and **Issue & save forecast**; with persistent disk, confirm saved forecast remains after restart.
5. Inspect the API errors in browser Console and the Render service logs when a request fails.
6. Open both URLs in an incognito window.

Important: a Vite environment variable is baked into the build. After changing `VITE_API_BASE_URL`, redeploy the **frontend**. `VITE_` values are public; never put tokens or secrets there. API endpoints that trigger data imports or save forecasts currently have no user login/rate-limiting; apply authentication, rate limits, monitoring, and budget controls before exposing this as a paid production service.

## Local dev

Leave `VITE_API_BASE_URL` unset. `npm run dev` proxies `/api` to `http://localhost:8000`. If you create `frontend/.env.local`, do not commit it.

**Repo layout note:** If GitHub shows a top-level `windsight/` directory with the app nested inside it, use `windsight/backend` and `windsight/frontend` as root directories instead.
