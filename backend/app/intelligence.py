"""Historical-error calibration and decision-risk signals. Pure, auditable calculations."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from math import isfinite
from statistics import mean

MIN_GLOBAL_POINTS = 32
MIN_GLOBAL_DAYS = 4
MIN_BUCKET_POINTS = 12
MIN_BUCKET_DAYS = 3
MIN_BACKTEST_POINTS = 48
MIN_BACKTEST_DAYS = 4


def percentile(values: list[float], proportion: float) -> float:
    ordered = sorted(values)
    if not ordered:
        raise ValueError("Cannot calculate a percentile without observations")
    index = (len(ordered) - 1) * proportion
    left = int(index)
    return ordered[left] + (ordered[min(left + 1, len(ordered) - 1)] - ordered[left]) * (index - left)


def block(start: str) -> str:
    hour = datetime.fromisoformat(start.replace('Z', '+00:00')).hour
    return ("00–06", "06–12", "12–18", "18–24")[hour // 6]


def build_samples(days: list[dict]) -> dict[str, list[tuple[str, float]]]:
    grouped: dict[str, list[tuple[str, float]]] = defaultdict(list)
    for day in days:
        if not day.get('available'):
            continue
        label = day['decision_date']
        for point in day['points']:
            sample = (label, point['error_mw'])
            grouped['all'].append(sample)
            grouped[block(point['start_time'])].append(sample)
    return grouped


def eligible(samples: list[tuple[str, float]], minimum_points: int, minimum_days: int) -> bool:
    return len(samples) >= minimum_points and len({label for label, _ in samples}) >= minimum_days


def estimate(forecast_mw: float, samples: list[tuple[str, float]]) -> dict:
    errors = [error for _, error in samples]
    lower, upper = percentile(errors, .10), percentile(errors, .90)
    # Winsorisation limits the influence of a few exceptional forecast misses.
    bounded = [min(max(error, lower), upper) for error in errors]
    shrinkage = len(errors) / (len(errors) + 32)
    correction = mean(bounded) * shrinkage
    correction = max(-forecast_mw, correction)
    p10_actual = max(0.0, forecast_mw + lower)
    p90_actual = max(p10_actual, forecast_mw + upper)
    return {
        'correction_mw': correction,
        'p10_actual_mw': p10_actual,
        'p90_actual_mw': p90_actual,
        'shortfall_likelihood_pct': 100 * sum(error < 0 for error in errors) / len(errors),
        'sample_count': len(errors),
        'sample_days': len({label for label, _ in samples}),
    }


def select_samples(samples: dict[str, list[tuple[str, float]]], hour_block: str):
    global_samples = samples.get('all', [])
    if not eligible(global_samples, MIN_GLOBAL_POINTS, MIN_GLOBAL_DAYS):
        return None, 'insufficient'
    local = samples.get(hour_block, [])
    if eligible(local, MIN_BUCKET_POINTS, MIN_BUCKET_DAYS):
        return local, 'six_hour_block'
    return global_samples, 'pooled'


def predict_profile(report: dict, calibration_days: list[dict], apply_correction: bool) -> list[dict]:
    samples = build_samples(calibration_days)
    output = []
    for point in report['forecast_profile']:
        forecast = point['forecast_mw']
        source, method = select_samples(samples, block(point['start_time']))
        row = {
            'start_time': point['start_time'], 'publish_time': point['publish_time'],
            'raw_forecast_mw': forecast, 'actual_mw': point.get('actual_mw'),
            'interval_minutes': point['interval_minutes'], 'model_source': method,
            'adjusted_forecast_mw': None, 'candidate_adjusted_mw': None,
            'p10_actual_mw': None, 'p90_actual_mw': None,
            'downside_buffer_mw': None, 'shortfall_likelihood_pct': None,
            'risk_tier': 'unavailable', 'sample_count': 0, 'sample_days': 0,
        }
        if source is not None:
            model = estimate(forecast, source)
            candidate = max(0.0, forecast + model['correction_mw'])
            buffer_mw = max(0.0, forecast - model['p10_actual_mw'])
            relative = buffer_mw / max(forecast, 500.0)
            row.update({
                'candidate_adjusted_mw': round(candidate, 2),
                'adjusted_forecast_mw': round(candidate, 2) if apply_correction else None,
                'p10_actual_mw': round(model['p10_actual_mw'], 2),
                'p90_actual_mw': round(model['p90_actual_mw'], 2),
                'downside_buffer_mw': round(buffer_mw, 2),
                'shortfall_likelihood_pct': round(model['shortfall_likelihood_pct'], 1),
                'risk_tier': 'elevated' if relative >= .20 else 'watch' if relative >= .10 else 'lower',
                'sample_count': model['sample_count'], 'sample_days': model['sample_days'],
            })
        output.append(row)
    return output


def backtest(pairs: list[tuple[dict, list[dict]]]) -> dict:
    baseline_error, candidate_error, covered = [], [], 0
    distinct = set()
    for observed, past in pairs:
        if not observed.get('available'):
            continue
        predicted = predict_profile(observed, past, apply_correction=False)
        for point in predicted:
            if point['candidate_adjusted_mw'] is None or point['actual_mw'] is None:
                continue
            distinct.add(observed['decision_date'])
            baseline_error.append(abs(point['actual_mw'] - point['raw_forecast_mw']))
            candidate_error.append(abs(point['actual_mw'] - point['candidate_adjusted_mw']))
            if point['p10_actual_mw'] <= point['actual_mw'] <= point['p90_actual_mw']:
                covered += 1
    ready = len(baseline_error) >= MIN_BACKTEST_POINTS and len(distinct) >= MIN_BACKTEST_DAYS
    base = mean(baseline_error) if baseline_error else None
    candidate = mean(candidate_error) if candidate_error else None
    delta = 100 * (base - candidate) / base if base and candidate is not None else None
    # Point adjustments are enabled only after a chronological, out-of-sample win.
    enabled = bool(ready and delta is not None and delta >= 1.0)
    return {
        'status': 'validated' if ready else 'insufficient_history',
        'adjustment_enabled': enabled, 'tested_days': len(distinct),
        'tested_intervals': len(baseline_error),
        'baseline_mae_mw': round(base, 2) if base is not None else None,
        'candidate_mae_mw': round(candidate, 2) if candidate is not None else None,
        'candidate_mae_improvement_pct': round(delta, 2) if delta is not None else None,
        'empirical_80pct_band_coverage_pct': round(100 * covered / len(baseline_error), 1) if baseline_error else None,
        'band_note': 'Empirical 10th–90th percentile scenarios; time-dependent errors mean 80% coverage is not guaranteed.',
    }


def analyse(target: dict, training: list[dict], backtest_result: dict) -> dict:
    all_samples = build_samples(training).get('all', [])
    train_dates = sorted({day for day, _ in all_samples})
    sufficient = eligible(all_samples, MIN_GLOBAL_POINTS, MIN_GLOBAL_DAYS)
    enabled = bool(sufficient and backtest_result['adjustment_enabled'])
    profile = predict_profile(target, training, enabled)
    with_bands = [point for point in profile if point['p10_actual_mw'] is not None]
    hours = lambda point: point['interval_minutes'] / 60
    raw_energy = sum(row['raw_forecast_mw'] * hours(row) for row in profile)
    adjusted_energy = sum(row['adjusted_forecast_mw'] * hours(row) for row in profile) if enabled and len(with_bands) == len(profile) and profile else None
    buffer = sum(row['downside_buffer_mw'] * hours(row) for row in with_bands)
    observed = [p for p in profile if p['actual_mw'] is not None and p['candidate_adjusted_mw'] is not None]
    signals = []
    if not sufficient:
        signals.append({'level':'info', 'title':'Awaiting historical calibration', 'detail':'Risk scenarios need at least four prior decision days and 32 matched observations. Unscored intervals remain unscored.'})
    else:
        elevated = sum(p['risk_tier'] == 'elevated' for p in with_bands)
        if elevated:
            signals.append({'level':'warning', 'title':f'{elevated} delivery intervals with elevated wind downside', 'detail':'Elevated means the empirical 10th-percentile downside is at least 20% of forecast MW (using a 500 MW denominator floor). Inspect the affected hours before making a purchasing decision.'})
        else:
            signals.append({'level':'info', 'title':'No elevated interval-level downside flags', 'detail':'Historical forecast-error scenarios still imply uncertainty; this is not evidence of zero supply risk.'})
        if enabled:
            signals.append({'level':'positive', 'title':'Bias adjustment supported by prior backtest', 'detail':'Chronological holdout shows at least 1% lower MAE than the original forecasts. Forecast corrections are still indicative, not dispatch instructions.'})
        else:
            signals.append({'level':'info', 'title':'Original forecasts retained', 'detail':'The correction layer is not activated until earlier walk-forward tests demonstrate improvement. Empirical downside scenarios remain visible.'})
    return {
        'decision_date': target['decision_date'], 'delivery_date': target['delivery_date'],
        'cutoff_time': target['cutoff_time'], 'source':'Elexon FUELHH + WINDFOR only',
        'status': 'ready' if sufficient else 'insufficient_history',
        'data_complete': target['available'],
        'training': {'sample_intervals': len(all_samples), 'sample_days': len(train_dates),
                     'first_decision_date': train_dates[0] if train_dates else None,
                     'last_decision_date': train_dates[-1] if train_dates else None,
                     'policy': 'Only prior January decisions ending at least one full calendar day before the selected cutoff. Timestamped late outturn revisions excluded.'},
        'backtest': backtest_result,
        'summary': {
            'forecast_intervals': len(profile), 'scored_intervals': len(observed),
            'scenario_intervals': len(with_bands),
            'elevated_risk_intervals': sum(p['risk_tier']=='elevated' for p in with_bands),
            'raw_forecast_mwh': round(raw_energy,2) if profile else None,
            'adjusted_forecast_mwh': round(adjusted_energy,2) if adjusted_energy is not None else None,
            'summed_interval_downside_buffer_mwh': round(buffer,2) if with_bands else None,
            'buffer_note': 'Sum of individual interval downside buffers; NOT an 80/90% quantile of total daily wind energy, demand shortfall, or a purchase recommendation.',
        },
        'signals': signals, 'profile': profile,
        'limitations': [
            'Historical residual scenarios are not a guaranteed predictive distribution or a weather forecast.',
            'Backtesting uses conservative day delays, but the source does not always expose actual publication timestamps; operational as-of availability cannot be proven for such records.',
            'Risk quantiles assume recent historical errors are informative; calibration is only within January 2026 and may be sparse.',
            'No demand, price, thermal generation or turbine SCADA feed; purchasing quantity and generation efficiency cannot be inferred.'
        ],
    }
