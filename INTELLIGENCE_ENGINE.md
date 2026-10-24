# WindSight Intelligence Engine

This layer sits **on top of** WindSight's unchanged Elexon source ingest and historical forecast-versus-outturn analysis. It is not a new data collection service, and it does not introduce third-party datasets or LLM API calls.

## Purpose and scope

For each January 2026 day-ahead decision, the engine uses **only earlier, historical Elexon forecast errors** to make the displayed wind forecast more actionable. It answers:

- What range of wind output is consistent with *previously observed* similar forecast errors?
- Which delivery intervals have a historically larger downside relative to the wind forecast?
- Does a simple empirical bias correction improve the original Elexon point forecast in tests on later, unseen days?
- Where is there too little historical data to support a risk estimate?

It does **not** know consumer demand, energy price, other generation, capacity limits or actual energy bought. **Downside buffers are wind forecasting scenarios, not megawatts to buy**.

## Data flow

```text
Elexon WINDFOR + FUELHH
       | (already implemented by WindSight)
       v
UTC timestamp normalisation and publication-cutoff selection
       v
Historical aligned forecast-versus-outturn pairs (MW)
       |            
       +--> Chronological, point-in-time training windows
                |
                +--> Six-hour UTC groups with pooled fallback
                +--> Winsorised, shrunken bias correction candidate
                +--> Empirical residual P10 / P90 scenarios
                +--> Walk-forward test: original MAE vs corrected MAE
                              |
                              +--> Enable adjustment only if tested benefit ≥1%
       v
Decision intelligence: intervals, observed data, downside flags and test evidence
```

## Decisions and leakage prevention

For a decision on date **D** at the selected Europe/London cutoff:

1. All forecast revisions must have `publishTime <= D cutoff`. This rule comes from the underlying WindSight selection function.
2. Calibration uses the **last 16 calendar decision dates at most**, ending at **D−2**. Their deliveries are therefore no later than D−1. This builds in a conservative one-calendar-day delay before an outturn is used. The available history is restricted to January 2026 for the hiring assignment.
3. For historical calibration and backtest scoring, when a FUELHH record exposes `publishTime`, outturn revisions after the target decision cutoff are filtered out. When `publishTime` is absent, the one-day delay is a **documented approximation**, not proof of real-world availability.
4. For each earlier backtest decision T, the correction is fitted using dates no later than **T−2**. T itself and future decisions are not used to fit the candidate.
5. Approval of a correction for D uses **only backtests with decisions dated no later than D−2**, i.e. results that should be available well before D under the delayed-outturn assumption.

### No invented coverage

Global calibration requires at least **32 matched interval comparisons across four distinct earlier decision dates**. For a six-hour UTC block, use local residuals only if that block includes at least **12 comparisons over three distinct historical decision dates**. Otherwise the full-period pooled error history is used. If global minimums are not met, all scenario and adjustment values remain `null`.

## Core calculations

Let the original forecast be **F** MW and the measured generation be **A** MW, both aligned to the forecast's duration.

**Signed error:** `E = A − F`. A negative error is an observed wind-generation shortfall relative to the forecast.

**Candidate bias-corrected forecast:** take earlier residuals for the same UTC six-hour block (or pooled residuals). Winsorise the 10th and 90th tails. Define `b = mean(winsorised E) × n / (n+32)`. The correction candidate is `max(0, F+b)`. The shrinkage means small samples exert less influence, and the lower bound prevents negative MW.

**Empirical output scenarios:** `P10_actual = max(0, F + P10(E))` and `P90_actual = max(P10_actual, F + P90(E))`. These are historical-residual scenarios, **not statistically guaranteed confidence intervals** or output from a meteorological forecasting model. The interval is likely to be unreliable under changing weather regimes or correlation and must be evaluated on holdout dates.

**Wind downside buffer per interval:** `max(0, F − P10_actual)` MW. The dashboard sums this value times each interval length into MWh. This **sum is not a joint quantile of daily wind production**.

**Past shortfall frequency:** historical count of `E < 0` divided by historical sample count, as a descriptive statistic; not a calibrated forecast probability.

**Risk labels** are product heuristics, not GB market standards: `ratio = buffer_mw / max(F, 500 MW)`. Elevated if ratio ≥ 20%, Watch if ≥ 10%, Lower otherwise. Always display the actual MW buffer and sample size when evaluating risk.

## Improvement gate

Chronological walk-forward validation starts only after an earlier eligible training window exists. Only if there are at least **48 unseen comparisons spanning at least four distinct test decision dates**, and the candidate reduces MAE by **at least 1%** versus raw forecasts, will adjusted forecasts appear in the dashboard. Otherwise `adjusted_forecast_mw` is `null` and the **original Elexon forecast remains the primary signal**.

A passed gate demonstrates relative performance only on the selected earlier January slices, **not out-of-sample accuracy under different months or future conditions**. The frontend displays baseline MAE, candidate MAE, test count and scenario-band coverage rather than making an unqualified accuracy claim.

## API

`GET /api/intelligence?day=2026-01-18&hour=9&minute=50`

The response contains:

- `training`: sample counts, date window and point-in-time policy
- `backtest`: original MAE, correction-candidate MAE, improvement, test coverage, whether correction is actually enabled
- `summary`: number of flagged intervals, forecast MWh, summed interval-level downside buffer MWh
- `profile`: original and optional adjusted point forecasts, empirical P10/P90 scenarios, historical shortfall frequency, risk tier and source evidence
- `signals`: **interpretation-oriented** warnings/information, never unsupported procurement instructions
- `limitations`: key data and modeling assumptions visible to reviewers

No extra network, database, queue, vendor AI key, scheduled retraining or sample-generated generation values are required.

## How to validate

From `backend/`:

```bash
python -m pytest -q tests
```

Tests include historical revision rejection, chronological backtesting, improvement gating, correction rejection when it worsens error, multi-day sample thresholds, missing observations, and future-date isolation. After real Elexon sync, inspect the intelligence dashboard on mid/late January decisions; early January is expected to display **insufficient history**, not fabricated confidence.

## Product boundaries

Wind forecast accuracy can improve with correction, but this is not guaranteed. The underlying generation is weather-dependent. Without a weather forecast or longer history, this implementation performs **point-in-time empirical post-processing and calibrated reporting**, not a physical forecast of wind from raw weather. Forecast intervals can share correlated errors, so simply summing their individual P10 values does not form an honest day-level P10. This limitation is intentional and shown to the user.


## Version 3 replay and live extension

The original January-specific `GET /api/intelligence` remains unchanged. New endpoint `GET /api/replay` and `GET /api/live` share the same error-estimation and backtest-gating functions. `backend/app/service.py::replay` computes a target forecast at its selected as-of cutoff, then creates calibration data from decisions at least two UK calendar days earlier. Walk-forward holdout calculations replay **each holdout's own cutoff**, rather than checking revisions against the final target's date. Historical target actuals appear only in the evaluation overlay.

`GET /api/live` uses the current London date and current UTC instant as cutoff for forecasts targeting tomorrow, with a warning after the N2EX 09:50 UK cutoff. When entering live mode, two recent publication-day snapshots are refreshed so cached forecasts are not mislabeled current. The UI checks for updates periodically. These do not constitute a certified low-latency power-market execution feed.

`POST /api/live/snapshot?cutoff=...` preserves the user's displayed timestamp; it only accepts timezone-aware cutoff instants from the current UK decision date within the prior 15 minutes. `backend/app/predictions.py` freezes the full interval estimate and backtest context. Later scoring aggregates actual 30-minute MW readings (averaging them for hourly predictions). Source interval completion and missing outturns are handled explicitly. A saved forecast cannot be overwritten through the exposed API, and risk data is not silently re-fitted after the result becomes known.

Forecast downside buffers are **MW differences**, not net supply deficits. Even high-looking buffer values do not automatically imply a market purchase: without demand, dispatchable generation commitments, contracts and market data, no feasible purchase instruction can be inferred from the assignment's two Elexon sources.
