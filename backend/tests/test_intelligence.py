from datetime import date, datetime, timedelta, timezone

from fastapi.testclient import TestClient
import app.main as http_app
from app.domain import Actual, Forecast, evaluate_day, timestamp
from app.intelligence import analyse, backtest, block, percentile, predict_profile
from app.service import WindService
from app.store import SnapshotStore


def make_report(day: date, error: float = -120, count: int = 24):
    tomorrow = day + timedelta(days=1)
    forecasts, actuals = [], []
    for hour in range(count):
        start = datetime(tomorrow.year, tomorrow.month, tomorrow.day, hour, tzinfo=timezone.utc)
        forecasts.append(Forecast(start, datetime(day.year, day.month, day.day, 8, 30, tzinfo=timezone.utc), 1000))
        actuals.extend([Actual(start, 1000 + error), Actual(start + timedelta(minutes=30), 1000 + error)])
    report = evaluate_day(day, forecasts, actuals)
    report['available'] = True
    return report


def test_percentile_and_utc_delivery_blocks():
    assert percentile([5, 1, 3], .5) == 3
    assert percentile([5, 1], .25) == 2
    assert block('2026-01-16T23:00Z') == '18–24'


def test_calibration_needs_four_distinct_days_even_with_many_intervals():
    past = [make_report(date(2026,1,1))]
    target = make_report(date(2026,1,5))
    rows = predict_profile(target, past, apply_correction=True)
    assert all(row['adjusted_forecast_mw'] is None for row in rows)
    assert all(row['risk_tier'] == 'unavailable' for row in rows)
    result = analyse(target, past, backtest([]))
    assert result['status'] == 'insufficient_history'
    assert result['summary']['summed_interval_downside_buffer_mwh'] is None


def test_conservative_error_calibration_and_risk_band():
    past = [make_report(date(2026,1,n)) for n in range(1,7)]
    target = make_report(date(2026,1,8))
    points = predict_profile(target, past, apply_correction=True)
    assert len(points) == 24
    assert points[0]['p10_actual_mw'] == 880
    assert points[0]['p90_actual_mw'] == 880
    assert points[0]['downside_buffer_mw'] == 120
    assert points[0]['shortfall_likelihood_pct'] == 100
    assert points[0]['adjusted_forecast_mw'] < 1000
    assert points[0]['adjusted_forecast_mw'] > 880  # correction is shrunk
    assert points[0]['model_source'] == 'six_hour_block'


def test_backtest_gates_real_improvement_and_rejects_unproven_layer():
    days = {date(2026,1,n):make_report(date(2026,1,n)) for n in range(1,16)}
    pairs = []
    for day in sorted(days)[6:]:
        past = [days[d] for d in sorted(days) if d <= day-timedelta(days=2)]
        pairs.append((days[day], past))
    result = backtest(pairs)
    assert result['status'] == 'validated'
    assert result['adjustment_enabled'] is True
    assert result['tested_intervals'] >= 48
    assert result['candidate_mae_mw'] < result['baseline_mae_mw']
    assert result['empirical_80pct_band_coverage_pct'] == 100
    zero = backtest([])
    assert zero['status'] == 'insufficient_history'
    assert zero['adjustment_enabled'] is False


def test_asof_actual_cutoff_drops_later_revision():
    day = date(2026,1,3)
    forecast = [Forecast(timestamp('2026-01-04T08:00Z'), timestamp('2026-01-03T08:30Z'), 1000)]
    actuals = [
        Actual(timestamp('2026-01-04T08:00Z'), 900, timestamp('2026-01-04T09:00Z')),
        Actual(timestamp('2026-01-04T08:00Z'), 600, timestamp('2026-01-20T11:00Z')),
        Actual(timestamp('2026-01-04T08:30Z'), 900, timestamp('2026-01-04T09:00Z')),
    ]
    historical = evaluate_day(day, forecast, actuals, actual_as_of=timestamp('2026-01-06T09:50Z'))
    latest = evaluate_day(day, forecast, actuals)
    assert historical['points'][0]['actual_mw'] == 900
    assert latest['points'][0]['actual_mw'] == 750


def seed_store(store: SnapshotStore, first: int = 1, last: int = 19):
    store.write('forecasts', date(2025,12,31), [])
    for number in range(first,last+1):
        day = date(2026,1,number)
        tomorrow = day + timedelta(days=1)
        forecasts = []
        actuals = []
        for hour in range(24):
            start = datetime(tomorrow.year,tomorrow.month,tomorrow.day,hour,tzinfo=timezone.utc)
            forecasts.append({'startTime':start.isoformat(),'publishTime':f'{day}T08:30:00Z','generation':1000})
            for minute in (0,30):
                actuals.append({'startTime':(start+timedelta(minutes=minute)).isoformat(),
                                'settlementDate':str(tomorrow),'fuelType':'WIND','generation':880})
        store.write('forecasts', day, forecasts)
        store.write('actuals', tomorrow, actuals)


def test_service_intelligence_is_asof_and_shows_validated_adjustment(tmp_path, monkeypatch):
    store = SnapshotStore(tmp_path)
    seed_store(store)
    service = WindService(store=store)
    before = service.intelligence(date(2026,1,18))
    assert before['status'] == 'ready'
    assert before['summary']['forecast_intervals'] == 24
    assert before['backtest']['adjustment_enabled'] is True
    assert before['profile'][0]['adjusted_forecast_mw'] < 1000
    assert before['training']['last_decision_date'] == '2026-01-16'
    assert before['summary']['elevated_risk_intervals'] == 0
    # Changing a later decision's forecast must never alter the Jan 18 intelligence view.
    store.write('forecasts', date(2026,1,19), [
        {'startTime':'2026-01-20T00:00:00Z','publishTime':'2026-01-19T08:30:00Z','generation':90000}
    ])
    after = service.intelligence(date(2026,1,18))
    assert before == after
    monkeypatch.setattr(http_app, 'service', service)
    client = TestClient(http_app.app)
    result = client.get('/api/intelligence?day=2026-01-18')
    assert result.status_code == 200
    assert result.json()['backtest']['tested_intervals'] > 0
    assert client.get('/api/intelligence?day=2026-02-04').status_code == 422


def test_missing_snapshot_produces_no_invented_recommendation(tmp_path):
    report = WindService(store=SnapshotStore(tmp_path)).intelligence(date(2026,1,8))
    assert report['status'] == 'insufficient_history'
    assert report['profile'] == []
    assert report['summary']['raw_forecast_mwh'] is None
    assert report['summary']['adjusted_forecast_mwh'] is None


def test_bias_correction_is_blocked_when_walkforward_makes_mae_worse():
    historic = [make_report(date(2026,1,n),error=-200) for n in range(1,9)]
    pairs = []
    for n in range(10,15):
        observed = make_report(date(2026,1,n),error=200)
        pairs.append((observed, historic))
    result = backtest(pairs)
    assert result['status'] == 'validated'
    assert result['candidate_mae_mw'] > result['baseline_mae_mw']
    assert result['adjustment_enabled'] is False
