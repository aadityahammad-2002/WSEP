# Demo note for WindSight v3

The original 10-minute Gridbricks video should primarily address the assignment's **January 2026** forecast-versus-outturn objectives. The extended replay/live workspaces are optional differentiation. They should be demonstrated only when real Elexon data is successfully imported and labelled correctly.

V3 optional demonstration: select a historic decision date, import its rolling window, inspect the reconstructed next-day forecast and the actual comparison chart, then review risk and the backtest gate. Switch to Live Prediction; import, issue a snapshot and reopen it from Saved Predictions. When a real delivery is complete, refresh outturn and show that the snapshot prediction does not move even when the current forecasting model might.

Do not claim a statistically calibrated 80% coverage rate, precise future errors, actual supply purchase instructions, or a validated live prediction uplift without out-of-sample source evidence.

---

# Submission video: 10-minute plan

**Record after the Elexon data sync succeeds. Do not present absent source values as real January measurements.**

## Part 1: Customer presentation — 4:45

**00:00–00:40 | Client problem**
An energy purchasing desk places orders before tomorrow's wind output is known. A raw wind forecast is not enough: the team must know exactly what was available before gate closure, and how wrong those forecasts usually are.

**00:40–01:25 | Source and context**
Show the January 2026 dashboard. Explain the selected decision date, following delivery date, and 09:50 GMT N2EX cutoff. State that source data comes exclusively from Elexon WINDFOR and FUELHH wind outturns.

**01:25–02:35 | Generation profile**
Change the decision date; show the wind forecast line, actual generation line, interval tooltips, and the timestamp at which the forecast was published. Explain that the buyer could only have seen eligible historical publications.

**02:35–03:40 | Forecast risk**
Show MAE, RMSE, signed bias, shortfall frequency, and exposure in MWh. Point out a negative error and explain that over-forecast wind can indicate an additional supply risk, but the app does not invent actual purchases.

**03:40–04:45 | Intelligence and takeaway**
Open the Decision intelligence tab. Identify one P10 downside interval, show sample evidence and whether the backtest activated correction. Show the sentence that this is not an instruction to buy any specific MW. Quickly mention revision audit and CSV export. Summarise: traceable as-of forecasts plus honest historical uncertainty.

## Part 2: Technical lead review — 4:45

**04:45–05:30 | Service boundaries**
Show architecture: React/Vite frontend, FastAPI API, asynchronous Elexon ingestor, day-partitioned raw snapshots, pure domain model. Explain why the pilot avoids a database, message broker, and synthetic analysis data.

**05:30–06:45 | As-of selection**
Open `backend/app/domain.py`, show `decision_instant` and `choose_forecasts`. Explain timezone-aware cutoff and latest eligible publication per delivery start. Show the cutoff-boundary and future-leakage tests.

**06:45–07:45 | Unit-safe error logic**
Show `evaluate_day` and `metrics`: two 30-minute actual MW values averaged for an hourly forecast; missing pair excluded; signed error, MAE, RMSE and MWh conversion. Distinguish measured exposure from procurement.

**07:45–08:40 | Intelligence layer and reliability**
Open `backend/app/intelligence.py`: explain that past residuals form scenario quantiles, that corrections are shrunk and tested on later unseen dates, and that poor or sparse results disable correction. Show source snapshots and API missing-data states. Run `python -m pytest -q tests` from `backend/`.

**08:40–09:30 | Build and handover**
Demonstrate `docker compose up --build`, GitHub Actions build/test workflow, the README and the deployed app. Call out known scope boundaries rather than overstating production readiness.

**09:30–09:45 | Wrap**
Name three high-value engineering decisions: no hindsight bias, no unit mismatch, and no unvalidated bias-correction claim. Keep total runtime under 10 minutes.
