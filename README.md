# WindSight

**UK day-ahead wind forecast, historical range analysis, advance contingency and frozen-prediction verification · v4**

WindSight reconstructs the wind generation forecast available when a British electricity utility would have placed its next-day power purchase order. It compares that forecast against actual wind output, measures systematic and extreme forecast error, and preserves a per-interval revision audit trail.

The project implements a React + FastAPI pilot scoped strictly to **Elexon WINDFOR and FUELHH / WIND**. It does **not** infer demand, non-wind supply, prices, trading volumes or purchase recommendations from data that does not exist in these two feeds.

## v4 — User-facing decision workspace

WindSight v4 separates **five operational views**:

1. **Historical replay**: choose one past decision date and the UK as-of cutoff, then view the next-day prediction and subsequent actuals. **Recalculate** now displays progress and a success/error message. It recomputes local snapshots; **Fetch required data** obtains source updates.
2. **Live prediction**: current available Elexon revisions, same correction/risk methodology, immutable **Issue & save** snapshots, and eventual actual-outturn scoring. A post-gate forecast is labeled monitoring, not a historical pre-gate purchasing decision.
3. **History · date range**: pick **From / To** dates, choose a decision cutoff, browse every date in pages of five, expand each day's chart and per-interval records, and export the visible page to CSV. **Fetch visible dates** imports up to five days plus their calibration history. A date range up to 366 calendar days is supported with paginated access.
4. **Forecast analytics / Decision intelligence**: the selected day can now be outside January; forecast versus actual, historical MAE, model evidence and wind contingency scenarios are displayed.
5. **Settlement records**: each interval exposes original forecast, engine prediction, actual wind, signed error, red/green outcome, scenario reserve, publication time and eligible revisions. CSV export includes the decision-time engine fields.

### Interpreting the numbers

- **Engine prediction (MW)** is the Elexon forecast unless a *prior chronological backtest* supports an adjustment. No invented wind generation values are used.
- **Signed error (MW)** = actual wind − the decision-time **engine** forecast. **Green** if actual ≥ engine estimate; **red** if actual < estimate; **neutral** if actuals not available yet.
- **Planning reserve scenario (MW)** = `max(engine_prediction_mw − historical_P10_scenario_mw, 0)`. Convert each interval to MWh by multiplying by its duration. It is calculated from data **known before delivery** and thus remains present even if actual generation ultimately **exceeds** prediction. If historical calibration is inadequate, this value is `null` and displayed as `—`.
- **Observed wind shortfall (MWh)** = `max(engine_prediction − actual, 0) × interval_hours`, calculable **after delivery only**. This is distinct from the *planning scenario* and cannot be used as tomorrow's purchase requirement.
- Neither measure specifies **additional electricity to buy**: that requires demand, contracted non-wind generation, reserve holdings and market costs not available from WINDFOR/FUELHH.

**Windows / VS Code (no Docker):** Open the extracted `windsight` folder. In one PowerShell terminal run `cd backend`, create a Python virtual environment (`py -3.13 -m venv .venv`), install `requirements-dev.txt`, and run `uvicorn` from that environment. In a second terminal run `cd frontend`, `npm install`, `npm run dev`. Open **http://localhost:5173**. Full commands are provided below.

For convenience, PowerShell scripts `scripts/start-backend.ps1` and `scripts/start-frontend.ps1` start each server from its own terminal. On systems restricting script execution, use the manual commands below rather than changing machine-wide execution policy.

**Source data:** Real Elexon imports require network access. If preserving your v3 raw data, copy the existing `backend/data/raw` and `backend/data/predictions` into v4 before startup; don't copy the old `.venv` or `node_modules` between machines. No fabricated Elexon observations ship in the ZIP. The test fixtures stay under `backend/tests/`.

### New backend endpoints

| HTTP route | Purpose |
| --- | --- |
| `GET /api/history?start=2026-09-01&end=2026-09-30&page=1&page_size=5` | Paginated daily + interval forecast, actual, signed error and pre-decision contingency scenario |
| `POST /api/history/prepare?start=2026-09-10&end=2026-09-14` | Asynchronous source + trailing calibration import for a visible page (max seven dates) |
| `GET /api/analysis/day?day=2026-09-10` | Reconstructed as-of comparison on any supported past date |
| `GET /api/analysis/intelligence?day=2026-09-10` | Replay-based intelligence evidence for the selected date |
| `GET /api/analysis/recent?day=2026-09-10` | Fourteen-day trend surrounding the selected decision |
| `GET /api/analysis/versions?day=2026-09-10&start=2026-09-11T09%3A00Z` | Forecast publication audit trail |
| `GET /api/analysis/export.csv?day=2026-09-10` | CSV with frozen as-of engine estimate and planning buffer |

**Verification:** 38 backend tests passed locally in this build environment, Python modules compiled and TypeScript/TSX source parsed without syntax errors. Dependency installation from npm failed due to DNS restrictions; **the full `npm run build` and browser integration were not verified**. Real Elexon acquisition, forecast model performance on production data, data-store backups, multi-instance synchronization, authentication, observability, and deployed service behaviour all require further evaluation. **Do not consider this a fully production-certified trading system.** See [QA_REPORT.md](QA_REPORT.md) and [V4_PRODUCT_SPEC.md](V4_PRODUCT_SPEC.md).

---

## New: two forecasting workspaces

**Historical replay** (`GET /api/replay`): choose any past UK decision date covered by Elexon, plus a cutoff time. The system reconstructs that day's forecast for the *following* UK delivery date from the publications available by the cutoff, builds error-based risk scenarios using only earlier available history, and shows actual outturn **after** prediction generation for side-by-side scoring. The original January 2026 challenge remains available via Forecast analytics, Decision intelligence, Settlement records and Methodology.

**Live prediction** (`GET /api/live`): obtains forecasts available as of the actual current UK time for **tomorrow**, calibrates against previous observed decisions, and labels elevated interval-level wind downside risk. Use **Issue & save forecast** to store an immutable snapshot of the exact values and model context that the user saw. Later, **Update actuals** downloads the corresponding FUELHH observations; the saved prediction is scored without being recomputed. Even if the current forecast changes, previously saved predictions remain unchanged.

Both use the same residual-based correction and walk-forward gate. A forecast correction is applied only if earlier time-ordered evaluation demonstrates MAE improvement. Without adequate sample evidence, the original Elexon forecast remains the point estimate, and unknown risk quantities are displayed as unavailable. A P10 downside gap expresses **possible wind under-delivery versus forecast**—**not** electricity purchases, contractual grid shortages, or an assured probability.

### Quick start: Windows / VS Code (no Docker)

**Terminal 1 (FastAPI):** from project root:

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

`tzdata` is included for Windows `ZoneInfo('Europe/London')`; no additional manual package install is needed on a fresh environment. Python 3.12 also works: replace `py -3.13` with `py -3.12` if installed. The Python interpreter already present in `.venv` can be reused.

**Terminal 2 (Vite):** open another terminal at project root:

```powershell
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. In **Historical replay**, select a past decision date and click **Fetch required data**; in **Live prediction**, do the same for today's forecast and the rolling calibration window. The importer makes real Elexon requests; about 34 publication days and up to 33 outturn days may need retrieval for an uncached date. Wait for import completion, then click **Recalculate**. The UI displays import errors and never fabricates missing values. Subsequent dates reuse cached JSON snapshots. An internet connection is required for first imports.

**To compare a saved prediction:** issue it on the Live tab. Once delivery observations are available, select that saved forecast and press **Update actuals**, then **Recalculate**. The resulting chart overlays the original baseline, frozen engine estimate and matched actuals. The backtest and raw power series remain traceable. Raw source files live under `backend/data/raw/`; issued snapshots are persisted under `backend/data/predictions/`.

**Note on the 09:50 gate:** Live Prediction uses *now*, including forecasts that may appear after the gate closes. The dashboard warns when the 09:50 local-UK gate has passed; a post-gate forecast must not be presented as a purchasable pre-gate forecast. Historical replay uses its chosen cutoff time explicitly. London DST transitions are reflected in expected intervals (23/25-hour days).

### v3 legacy API (maintained)

| Endpoint | Purpose |
| --- | --- |
| `POST /api/prepare?day=2026-09-10` | Async import for selected decision date + rolling earlier data |
| `GET /api/replay?day=2026-09-10&hour=9&minute=50` | Reconstructed next-day forecast, uncertainty, actuals, backtest |
| `GET /api/live` | Tomorrow's wind outlook from current Elexon publications |
| `POST /api/live/snapshot` | Freeze and persist currently available live prediction |
| `GET /api/predictions` | List saved prediction IDs |
| `GET /api/predictions/{id}` | Compare original saved prediction against imported actuals |
| `POST /api/predictions/{id}/refresh-actual` | Fetch updated outturns for one saved prediction |

**Scope and evidence:** live ingestion and real-world accuracy were not verified against current Elexon values in the build environment. Charts show no fabricated output. Historical replay cannot guarantee exact historical *actual-publication availability* if Elexon actual revisions lack timestamps. Scenario percentiles are empirical residual estimates, not statistically validated probabilistic forecasts. This remains a demonstration/pilot rather than an autonomously executing trading system.

## Decision intelligence upgrade

The original January 2026 Elexon forecast-accuracy challenge remains intact. WindSight also includes an optional **Decision intelligence** workspace that turns historical forecast-error comparisons into **auditable wind downside scenarios and cautious, backtest-gated bias corrections**. This is an explanatory engine, not a chatbot or a power purchasing optimiser.

- Reconstructs earlier forecast revisions at the actual decision cutoff and deliberately uses a delayed historical training window.
- Computes residual P10/P90 scenarios by six-hour UTC delivery block, with pooled fallback and explicit insufficient-sample handling.
- Flags intervals with historically higher downside risk and shows a per-interval MW buffer. The sum in MWh is **not** a procurement recommendation or the quantile of total daily output.
- Compares corrections versus original forecasts on strictly earlier walk-forward test dates, **activating the corrected point forecast only if it passes the minimum sample and improvement tests**.
- Keeps historical sample counts, test metrics and limitations visible on screen. Extra features never replace the underlying Elexon baseline comparison.

See [INTELLIGENCE_ENGINE.md](INTELLIGENCE_ENGINE.md) for exact equations, thresholds, as-of assumptions, validation and caveats. **These heuristics are implementation choices, not additional mandatory requirements in the assignment.**

## Optional Docker deployment (not required for local development)

Requires Docker Engine with Compose and internet access to fetch Elexon data.

```bash
docker compose up --build
```

Open **http://localhost:8000**. The container may start the fixed January 2026 pilot import when AUTO_SYNC_ON_START=1; the new historical/live workspaces import data on demand. The UI shows progress and never labels fictional values as observations. The downloaded raw snapshots are persisted in `backend/data/raw/` via a bind mount.

For the original January pilot, run `python -m app.cli sync`. For replay/live, use **Fetch required data**. Subsequent starts reuse imported snapshots. The Elexon API has no API-key requirement; the first sync can take several minutes depending on their rate limits.

## Local development

Backend:

```bash
cd backend
python -m venv .venv
# Activate .venv in your shell (Windows: .venv\Scripts\activate)
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

In another terminal:

```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite proxies `/api` to localhost:8000. Click **Fetch selected date**, or run a one-time January pilot import from the backend directory:

```bash
python -m app.cli sync
python -m app.cli verify
```

The sync/verification exits nonzero if a day cannot be retrieved or has no comparable intervals. `verify` prints loaded dates, matched records, and rejected source rows. Retry safely; already downloaded source-day snapshots are reused. Use `--force` to re-fetch the published source records.

## API

| Route | Result |
| --- | --- |
| `GET /api/health` | Health/version |
| `GET /api/intelligence?day=2026-01-18&hour=9&minute=50` | Original January-only downside scenarios, correction gate and evidence |
| `GET /api/status` | Days loaded, import progress and source failures |
| `POST /api/sync` | Start asynchronous import (`?force=true` replaces snapshots) |
| `GET /api/comparison?day=2026-01-15&hour=9&minute=50` | As-of forecast profile (including unmatched intervals), joined outturn and daily metrics |
| `GET /api/metrics?hour=9&minute=50` | Monthly aggregates and daily MAE history |
| `GET /api/forecast-versions?day=2026-01-15&start=2026-01-16T09%3A00Z` | Publication history for a forecast time |
| `GET /api/export.csv?day=2026-01-15` | Matched interval records as a CSV |

Interactive API documentation: `http://localhost:8000/docs`.

## Exact analysis rules

1. **Decision date**: every calendar day from **2026-01-01 to 2026-01-31**, inclusive. **Delivery**: the **following calendar day in Europe/London**, through 2026-02-01. January is in GMT; date and time semantics are explicit rather than inferred from the server's timezone.
2. **Decision cutoff**: configurable, default **09:50 Europe/London** for the N2EX UK day-ahead gate closure. Only forecast entries with `publishTime <= cutoff` are candidates. For each delivery `startTime`, take the latest eligible `publishTime`.
3. **Data origin**: WINDFOR raw dataset history is requested by **publication date**, including the previous day as fallback for older still-eligible forecasts; FUELHH observations are requested by **settlement date** and filtered to `fuelType=WIND`. An incomplete or empty response is never substituted with a generated time series.
4. **Resolution**: select the native forecast interval (30 or 60 minutes) from consecutive delivery timestamps. FUELHH is a 30-minute **mean MW** measurement. For an hourly forecast, take the average of the two complete half-hour actual readings; **do not sum MW**. A missing half-hour invalidates the hourly comparison. For a 30-minute forecast use its corresponding FUELHH half-hour. In ambiguous sparse cases, treat WINDFOR as hourly and mark the resolution as an assumption.
5. **Actual revisions**: where multiple actual readings share `startTime`, use the record with the latest provided publication timestamp. Keep source files separately so values remain auditable.
6. **Signed error** = actual MW − forecast MW. A negative value is a wind **shortfall**. `MAE = mean(abs(error))`; `RMSE = sqrt(mean(error²))`; `bias = mean(error)`; P90 absolute error uses linear interpolation; shortfall frequency is `count(error < 0) / matched_count`.
7. **Shortfall exposure (MWh)** = `sum(max(forecast MW − actual MW, 0) × interval_hours)` over matched intervals. This is a *wind forecasting exposure*, not electricity that the utility necessarily purchased. No actual purchase requirement can be calculated without demand and other supply information.
8. **Coverage** reports observed matched interval count against expected delivery intervals at the inferred native forecast interval. Missing data is explicit. Monthly metrics aggregate all valid observed delivery intervals; monthly completeness separately reports how many of the 31 days are present.

### Model assumptions and limitations

- The benchmark is operational metered Elexon forecast versus Elexon outturn; they need not cover every physically generated MW in Britain. Forecast error should therefore be understood as **error between the specified datasets**, not the utility's metered imbalance.
- The original January endpoints remain available for assignment verification, while v4 interactive views accept any supported historical decision date; live claims remain conditional on successful current-source sync, and do not substitute simulated observations.
- The application computes ex-post validation of the forecast that was available at gate closure. When interpreting historical performance, only use actuals for evaluation *after* delivery.
- The snapshot store is local and immutable per source day until the user explicitly refreshes it. It supports a fixed-month pilot without introducing a database dependency. Cloud platforms with ephemeral filesystems will re-import on restart unless persistent storage or preloaded snapshots are configured.
- A sparse day without adjacent intervals defaults to the documented hourly forecast resolution. `resolution_inferred=false` identifies this assumption; missing actual half-hours remain unmatched.

## Project structure

```text
backend/
  app/
    domain.py      # Pure timestamp, selection, matching and error calculations
    intelligence.py # Historical calibration, downside scenarios, walk-forward tests
    predictions.py  # Immutable live-forecast snapshots and later outturn scoring
    elexon.py      # Elexon async client with retry for rate limits
    store.py       # Atomic raw JSON day-partitioned snapshots
    service.py     # Day/month analytics, import orchestration, audit history
    main.py        # FastAPI REST API, CSV download and SPA hosting
    cli.py         # One-time data import command
  data/raw/        # Persisted source-day snapshots, written on first sync
  data/predictions/ # Saved live forecast snapshots (excluded from Git)
  tests/           # Domain, model-gating, replay/live and API regression tests
  requirements.txt
  Dockerfile
frontend/
  src/
    App.tsx        # Original challenge views and navigation
    ForecastWorkspace.tsx # Historical replay and live snapshot dashboard
    api.ts         # HTTP client with explicit errors
    types.ts       # API response contracts
    styles.css     # Responsive visual system
  package.json
.github/workflows/ci.yml
heroku.yml
docker-compose.yml
scripts/publish_github.sh  # Public anonymous GitHub publication helper
```

## Test and build

```bash
cd backend
pip install -r requirements-dev.txt
pytest -q tests
```

```bash
cd frontend
npm install
npm run build
```

The CI workflow is configured to execute both on pushes and pull requests. Tests cover future-data leakage, publication-cutoff equality, hourly averaging vs. power summing, missing half-hours, January/February boundary, signed metrics, outturn revisions, API contracts and CSV export.

## Publish the anonymous GitHub repository

After inspecting the code and running the tests, authenticate locally using `gh auth login` and execute from the project root:

```bash
bash scripts/publish_github.sh random-nonidentifying-repo-name
```

The helper commits source and CI, then creates and pushes the public repo. `.gitignore` excludes Elexon downloads, local secrets and caches. Confirm the public repo in a logged-out/incognito session. If a repository already exists, use normal `git push` rather than the create helper.

## Deployment (Heroku with Docker)

The provided **`heroku.yml` and multi-stage Dockerfile** build the React bundle and serve both SPA + API as a single web dyno. Heroku requires a user account and a paid dyno to run consistently. From an authenticated Heroku CLI session, in the repository root:

```bash
heroku create your-anonymous-app-name
heroku stack:set container -a your-anonymous-app-name
git push heroku main
```

Verify deployment at `https://your-anonymous-app-name.herokuapp.com` and `/api/health`. Docker's default `AUTO_SYNC_ON_START=1` starts historical import on boot; Heroku's ephemeral filesystem means snapshots will be retrieved on dyno replacement. For a persistent pilot, run the one-time sync in your local backend, include verified snapshot JSON in the deployment build context, and commit only source-distributable datasets after checking the data licence.

> **Submission link:** Only paste the URL of a deployment that you actually created and verified in an incognito browser. Do not present the above example hostname as a live URL.

## Sources

- [Elexon WINDFOR stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/WINDFOR/stream)
- [Elexon FUELHH stream](https://bmrs.elexon.co.uk/api-documentation/endpoint/datasets/FUELHH/stream)
- [Nord Pool N2EX auction timing](https://support.nordpoolgroup.com/support/solutions/articles/8000088463-about-the-n2ex-day-ahead-auction)

## AI-tool use disclosure

AI tools were used for implementation assistance, including UI scaffolding, code drafting, risk-model design, replay/live feature development and test suggestions. The forecast-selection and power-error calculations are explicit in `domain.py` and have deterministic tests in `tests/`. As with any submission, the person presenting the work must independently inspect, understand and verify it, especially the external Elexon integration.

## Submission checklist

- [ ] Run `python -m app.cli verify` successfully after downloading all 32 forecast publication days (2025-12-31 through 2026-01-31) and 31 actual delivery days (2026-01-02 through 2026-02-01)
- [ ] Run backend tests and frontend build in a network-connected environment
- [ ] Deploy the app to Heroku and open its URL in incognito
- [ ] Create a public GitHub repository with an anonymous/random name and verify read access
- [ ] Record an **unlisted YouTube video under 10 minutes**: client-facing pilot demo first (up to five), code/architecture/engineering review second (up to five)
- [ ] Submit the GitHub URL, deployment URL and YouTube URL through the company's challenge form, checking access in incognito


### Navigation scopes

- **Historical replay** is date-selectable; it reconstructs next-day predictions using only data known by the selected decision cutoff.
- **Live prediction** operates using the currently available Elexon publications.
- **Forecast analytics**, **Decision intelligence**, and **Settlement records** now use a selected historical decision date, while the original January-only API endpoints remain available for the hiring challenge.
- The top-right header indicates the active workspace rather than labeling every page as a January pilot.
