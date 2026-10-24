# WindSight v4 — verification report

## Verified in the build environment

| Check | Status |
| --- | --- |
| Python backend test suite | **38 passed** (`PYTHONPATH=backend pytest -q backend/tests`) |
| New date-range pagination, input bounds, no fabricated data | Passed |
| Planning reserve persists when actual wind exceeds prediction | Passed |
| Negative signed error and observed shortfall separated from advance reserve | Passed |
| Snapshot cache sees source replacement | Passed |
| Existing as-of historical forecast, DST and frozen live snapshots | Passed (regressions) |
| FastAPI import and Python module compilation | Passed |
| Frontend `.ts` and `.tsx` syntax parser | Passed |
| Frontend dependency installation and `npm run build` | **Not verified**; npm registry DNS `EAI_AGAIN` |
| Actual Elexon January/October observations and live forecasts | **Not fetched/validated** in this sandbox |
| Real Windows/browser end-to-end | **Needs local test** |
| Public deployed environment and account security | **Not deployed; not production-certified** |

## Local verification commands (PowerShell)

Terminal A, from extracted project root:

```powershell
cd backend
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q tests
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000
```

Terminal B:

```powershell
cd frontend
npm install
npm run build
npm run dev
```

Open `http://localhost:5173`. In **Historical replay**, select a loaded date, press **Recalculate** and verify that it displays feedback. To update sources use **Fetch required data**. In **History**, choose a date range, press **Fetch visible dates**, watch the sync progress, expand a day and verify the interval chart, signed error colours, `—` for missing actuals/scenario calibration, and the pre-decision buffer. Download the visible page CSV and cross-check rows. In **Live prediction**, issue a snapshot and confirm the ID remains stable after source refresh.

API smoke tests:

```powershell
Invoke-RestMethod http://localhost:8000/api/health
Invoke-RestMethod 'http://localhost:8000/api/history?start=2026-09-10&end=2026-09-12&page=1'
Invoke-RestMethod 'http://localhost:8000/api/analysis/intelligence?day=2026-09-10'
```

## Remaining gaps

1. Real Elexon ingestion and historical backtest are unverified for deployed data; never infer improved accuracy from synthetic regression test results.
2. Browser layout has not been manually exercised at tablet/mobile sizes; check responsive table scrolling, date input localization and Vite hot reload.
3. A publicly accessible production deployment needs authentication, quotas, persistent storage, backups, monitoring and disaster recovery.
4. Historical snapshot reruns may vary if the underlying upstream actual history is revised without publication timestamps. Frozen live snapshots are immutable, but as-of actual reconstruction cannot always be guaranteed.
5. The planning reserve is **not** an instruction to buy energy. No consumer demand, trading position or market cost data have been added.
