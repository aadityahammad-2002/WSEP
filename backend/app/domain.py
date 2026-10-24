"""Forecast selection and power-error calculations. No network or storage dependencies."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from math import isfinite, sqrt
from statistics import mean
from zoneinfo import ZoneInfo

UTC = timezone.utc
LONDON = ZoneInfo("Europe/London")
FIRST_DECISION = date(2026, 1, 1)
LAST_DECISION = date(2026, 1, 31)


@dataclass(frozen=True)
class Forecast:
    start: datetime
    published: datetime
    mw: float


@dataclass(frozen=True)
class Actual:
    start: datetime
    mw: float
    published: datetime | None = None


def timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"Timezone missing: {value}")
    return parsed.astimezone(UTC)


def power(value: object) -> float:
    if isinstance(value, bool):
        raise ValueError("Invalid power reading")
    number = float(value)
    if not isfinite(number) or number < 0:
        raise ValueError("Power must be a finite, nonnegative MW value")
    return number


def parse_forecasts(rows: list[dict]) -> tuple[list[Forecast], int]:
    parsed, invalid = [], 0
    for row in rows:
        try:
            parsed.append(Forecast(timestamp(row["startTime"]), timestamp(row["publishTime"]), power(row["generation"])))
        except (TypeError, ValueError, KeyError, AttributeError):
            invalid += 1
    return parsed, invalid


def parse_actuals(rows: list[dict]) -> tuple[list[Actual], int]:
    parsed, invalid = [], 0
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        if row.get("fuelType") != "WIND":
            continue
        try:
            published = timestamp(row["publishTime"]) if row.get("publishTime") else None
            parsed.append(Actual(timestamp(row["startTime"]), power(row["generation"]), published))
        except (TypeError, ValueError, KeyError, AttributeError):
            invalid += 1
    return parsed, invalid


def decision_instant(day: date, hour: int = 9, minute: int = 50, allow_any_day: bool = False) -> datetime:
    if not allow_any_day and not FIRST_DECISION <= day <= LAST_DECISION:
        raise ValueError("Decision date must be within January 2026")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError("Invalid decision time")
    return datetime.combine(day, time(hour, minute), tzinfo=LONDON).astimezone(UTC)


def choose_forecasts(forecasts: list[Forecast], cutoff: datetime, delivery: date) -> dict[datetime, Forecast]:
    selected: dict[datetime, Forecast] = {}
    for item in forecasts:
        # Forecasts issued after gate closure cannot have informed that decision.
        if item.published > cutoff or item.start.astimezone(LONDON).date() != delivery:
            continue
        previous = selected.get(item.start)
        if previous is None or item.published > previous.published:
            selected[item.start] = item
    return selected


def interval_minutes(selected: dict[datetime, Forecast]) -> int:
    starts = sorted(selected)
    gaps = [int((b - a).total_seconds() / 60) for a, b in zip(starts, starts[1:])]
    # WINDFOR is normally hourly; sparse imports are not evidence of 30-minute data.
    return 30 if 30 in gaps else 60


def metrics(points: list[dict], expected: int) -> dict:
    if not points:
        return {
            "count": 0, "expected": expected, "coverage_pct": 0.0,
            "mae_mw": None, "rmse_mw": None, "bias_mw": None,
            "p90_abs_error_mw": None, "shortfall_frequency_pct": None,
            "shortfall_mwh": None, "mean_forecast_mw": None, "mean_actual_mw": None,
        }
    errors = [p["error_mw"] for p in points]
    absolutes = sorted(abs(value) for value in errors)
    rank = 0.9 * (len(absolutes) - 1)
    low = int(rank)
    fraction = rank - low
    p90 = absolutes[low] * (1 - fraction) + absolutes[min(low + 1, len(absolutes) - 1)] * fraction
    return {
        "count": len(points), "expected": expected,
        "coverage_pct": round(100 * len(points) / expected, 2) if expected else 0,
        "mae_mw": round(mean(absolutes), 2),
        "rmse_mw": round(sqrt(mean([v * v for v in errors])), 2),
        "bias_mw": round(mean(errors), 2),
        "p90_abs_error_mw": round(p90, 2),
        "shortfall_frequency_pct": round(100 * sum(v < 0 for v in errors) / len(errors), 2),
        # This is wind forecast shortfall exposure, not electricity bought or purchased.
        "shortfall_mwh": round(sum(max(-p["error_mw"], 0) * p["interval_minutes"] / 60 for p in points), 2),
        "mean_forecast_mw": round(mean(p["forecast_mw"] for p in points), 2),
        "mean_actual_mw": round(mean(p["actual_mw"] for p in points), 2),
    }


def evaluate_day(day: date, forecasts: list[Forecast], actuals: list[Actual], hour: int = 9, minute: int = 50, actual_as_of: datetime | None = None, allow_any_day: bool = False, cutoff_override: datetime | None = None) -> dict:
    cutoff = cutoff_override or decision_instant(day, hour, minute, allow_any_day=allow_any_day)
    if cutoff.tzinfo is None:
        raise ValueError("Cutoff must include a timezone")
    if cutoff.astimezone(LONDON).date() != day:
        raise ValueError("Cutoff must fall on the selected UK decision date")
    cutoff = cutoff.astimezone(UTC)
    delivery = day + timedelta(days=1)
    selected = choose_forecasts(forecasts, cutoff, delivery)
    interval = interval_minutes(selected)

    # Revisions of FUELHH observations are resolved by publication time where available.
    measured: dict[datetime, Actual] = {}
    for actual in actuals:
        # Ignore later outturn revisions when reconstructing a past training cutoff.
        if actual_as_of is not None and actual.published is not None and actual.published > actual_as_of:
            continue
        prior = measured.get(actual.start)
        if prior is None or (actual.published or datetime.min.replace(tzinfo=UTC)) > (prior.published or datetime.min.replace(tzinfo=UTC)):
            measured[actual.start] = actual

    points = []
    profile = []
    for start, forecast in sorted(selected.items()):
        samples = [measured.get(start + timedelta(minutes=30 * k)) for k in range(interval // 30)]
        base = {
            "start_time": start.isoformat().replace("+00:00", "Z"),
            "publish_time": forecast.published.isoformat().replace("+00:00", "Z"),
            "forecast_mw": round(forecast.mw, 2),
            "interval_minutes": interval,
        }
        if any(sample is None for sample in samples):
            # Keep the published forecast visible; missing outturn cannot be scored.
            profile.append({**base, "actual_mw": None, "error_mw": None})
            continue
        actual_mw = mean(sample.mw for sample in samples if sample is not None)
        error = actual_mw - forecast.mw
        point = {
            **base,
            "actual_mw": round(actual_mw, 2),
            "error_mw": round(error, 2),
            "absolute_error_mw": round(abs(error), 2),
            "shortfall_mw": round(max(forecast.mw - actual_mw, 0), 2),
        }
        points.append(point)
        profile.append(point)

    # UK daylight-saving transitions produce 46 or 50 half-hour delivery periods.
    delivery_start = datetime.combine(delivery, time.min, tzinfo=LONDON).astimezone(UTC)
    delivery_end = datetime.combine(delivery + timedelta(days=1), time.min, tzinfo=LONDON).astimezone(UTC)
    expected = int((delivery_end - delivery_start).total_seconds() / (interval * 60))
    return {
        "decision_date": day.isoformat(), "delivery_date": delivery.isoformat(),
        "cutoff_time": cutoff.isoformat().replace("+00:00", "Z"),
        "resolution_minutes": interval, "resolution_inferred": any(
            int((b - a).total_seconds() / 60) in (30, 60)
            for a, b in zip(sorted(selected), sorted(selected)[1:])
        ), "selected_forecasts": len(selected),
        "actual_observations": len(measured), "missing_actual_intervals": len(profile) - len(points),
        "metrics": metrics(points, expected), "points": points, "forecast_profile": profile,
    }


def versions_for(start: datetime, rows: list[Forecast], cutoff: datetime) -> list[dict]:
    versions = sorted((item for item in rows if item.start == start), key=lambda x: x.published)
    return [
        {"publish_time": x.published.isoformat().replace("+00:00", "Z"),
         "generation_mw": x.mw, "eligible": x.published <= cutoff}
        for x in versions
    ]
