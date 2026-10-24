# WindSight v4 — operational scope and acceptance criteria

## User workflows

### Historical replay

Select a past decision date and UK local cutoff; retrieve the Elexon WINDFOR revisions that were published before that cutoff and predict the *following* delivery date. Actual FUELHH generation is joined for ex-post scoring only. A manual **Recalculate** button must show feedback; source re-import is a separate, explicitly visible action.

### History — selected date range

Select start and end decision dates, up to 366 days. The report is paginated, newest date first, with five daily cards per page. Expand each day to review all delivery intervals: Elexon baseline, point forecast, actual wind, signed error, red/green/unknown outcome, and downside planning scenario. UK daylight-saving duplicated clock labels carry BST/GMT to disambiguate them. A CSV export corresponds only to the current visible page, with clear naming. Import applies to the visible set of dates and its rolling calibration history.

### Live prediction

Show the forecast currently available from Elexon. Future actuals must remain blank, never shown as zero. Saving a live prediction records the forecast, decision timestamp, empirical scenario evidence and model version. Later FUELHH actuals are scored against the *original saved forecast*, not the latest recalculation.

### Decision intelligence and settlement records

Provide selected-date MAE/bias, forecast-vs-engine-vs-actual charts, backtest gate evidence, interval errors and revision history. Historical data date filters are not restricted to the January pilot. The original challenge's January endpoints remain supported.

## Business rules

* Error: **actual − engine prediction** in MW. Red if negative, green if zero/positive, neutral when actual not loaded.
* Advance reserve scenario: `max(engine MW − P10 MW, 0)`; if empirical P10 not supported, `null`, *not zero*.
* Observed shortfall exposure: `max(engine MW − actual MW, 0) × delivery_interval_hours` in MWh.
* Once generated for a given historical decision cutoff, the advance reserve scenario **does not depend on the eventual actual outcome**. Even if actual > engine prediction (green), the pre-decision buffer remains as an audit of the arrangement risk that existed beforehand.
* It is **incorrect** to describe this reserve as mandatory purchase volume. WIND-only datasets lack the company's demand, hedged position, contracted assets, financial limits and balancing constraints.
* Missing forecast/actual readings remain missing; no synthetic Elexon data are inserted into live/history response objects.
* DST in the UK creates non-48 settlement-day lengths. UTC delivery interval timestamps are used for joins and exports; local clock labels show BST/GMT where needed.

## Acceptance tests

- Date-range pagination across month boundaries returns correctly ordered decisions and total pages.
- Invalid date ranges are rejected with 422, including reverse order, >366 days, and excessively large page size.
- If 1000 MW was predicted, actual is 1300 MW and historical P10 is 800 MW, error is **+300 MW (green)** and planning reserve is **200 MW**, observed shortfall **0 MWh** for a one-hour interval.
- If 1000 MW was predicted, actual is 700 MW and P10 is 850 MW, error is **−300 MW (red)**, planned buffer **150 MW**, observed shortfall **300 MWh** for a one-hour interval.
- Real data are retrieved only from Elexon WINDFOR and FUELHH. Backtest correction is enabled only when held-out MAE improves.
- Frozen live predictions never change when actuals are subsequently downloaded.
- Manual Recalculate displays loading and completion/error states.

## Before serving real customers

This is a tested development release, not a security- or trading-certified production system. Verify npm production build and cross-browser UI, real Elexon response schemas/rate limits, cutoff handling and actual revision timestamps with current source records. Add account authentication/authorization, tenant separation, request quotas, persistent durable task queues and databases, audit logging, observability, backups, incident playbooks and calibrated real-data backtests before operational deployment or financial decisions.
