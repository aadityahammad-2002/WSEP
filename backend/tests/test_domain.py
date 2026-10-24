from datetime import date, datetime, timedelta, timezone
from math import sqrt

import pytest

from app.domain import (
    Actual, Forecast, choose_forecasts, decision_instant, evaluate_day,
    metrics, parse_actuals, parse_forecasts, power, timestamp,
)

UTC = timezone.utc


def at(value: str) -> datetime:
    return timestamp(value)


def sample_forecast(time: str, published: str, mw: int = 1000) -> Forecast:
    return Forecast(at(time), at(published), mw)


def sample_actual(time: str, mw: int = 900) -> Actual:
    return Actual(at(time), mw)


def test_latest_eligible_forecast_ignores_future_publications():
    delivery = date(2026, 1, 16)
    forecasts = [
        sample_forecast('2026-01-16T10:00Z', '2026-01-15T08:30Z', 1000),
        sample_forecast('2026-01-16T10:00Z', '2026-01-15T09:49Z', 1300),
        sample_forecast('2026-01-16T10:00Z', '2026-01-15T10:30Z', 2000),
        sample_forecast('2026-01-17T10:00Z', '2026-01-15T08:30Z', 900),
    ]
    chosen = choose_forecasts(forecasts, decision_instant(date(2026, 1, 15)), delivery)
    assert len(chosen) == 1
    assert chosen[at('2026-01-16T10:00Z')].mw == 1300


def test_exactly_at_gate_close_is_eligible():
    forecast = sample_forecast('2026-01-02T00:00Z', '2026-01-01T09:50Z', 900)
    chosen = choose_forecasts([forecast], decision_instant(date(2026, 1, 1)), date(2026, 1, 2))
    assert chosen[forecast.start] == forecast


def test_hourly_forecast_aggregates_two_half_hour_actuals_without_summing_power():
    forecasts = [
        sample_forecast('2026-01-16T08:00Z', '2026-01-15T08:30Z', 1200),
        sample_forecast('2026-01-16T09:00Z', '2026-01-15T08:30Z', 1000),
    ]
    actuals = [
        sample_actual('2026-01-16T08:00Z', 1000),
        sample_actual('2026-01-16T08:30Z', 800),
        sample_actual('2026-01-16T09:00Z', 700),
        sample_actual('2026-01-16T09:30Z', 900),
    ]
    report = evaluate_day(date(2026, 1, 15), forecasts, actuals)
    assert report['resolution_minutes'] == 60
    assert report['metrics']['count'] == 2
    assert report['points'][0]['actual_mw'] == 900  # (1000 + 800) / 2
    assert report['metrics']['bias_mw'] == -250
    assert report['metrics']['mae_mw'] == 250
    assert report['metrics']['shortfall_mwh'] == 500


def test_half_hour_uses_the_matching_observation():
    forecasts = [
        sample_forecast('2026-01-16T07:00Z', '2026-01-15T08:30Z', 100),
        sample_forecast('2026-01-16T07:30Z', '2026-01-15T08:30Z', 110),
    ]
    actuals = [sample_actual('2026-01-16T07:00Z', 80), sample_actual('2026-01-16T07:30Z', 120)]
    report = evaluate_day(date(2026, 1, 15), forecasts, actuals)
    assert report['resolution_minutes'] == 30
    assert report['metrics']['count'] == 2
    assert report['metrics']['bias_mw'] == -5
    assert report['metrics']['shortfall_mwh'] == 10


def test_missing_second_half_hour_does_not_turn_into_partial_hour():
    forecasts = [
        sample_forecast('2026-01-16T08:00Z', '2026-01-15T08:30Z', 100),
        sample_forecast('2026-01-16T09:00Z', '2026-01-15T08:30Z', 100),
    ]
    report = evaluate_day(date(2026, 1, 15), forecasts, [sample_actual('2026-01-16T08:00Z', 100)])
    assert report['points'] == []
    assert report['metrics']['mae_mw'] is None


def test_january_31_decision_evaluates_february_1_delivery():
    forecasts = [sample_forecast('2026-02-01T10:00Z', '2026-01-31T08:30Z')]
    actuals = [sample_actual('2026-02-01T10:00Z'), sample_actual('2026-02-01T10:30Z')]
    report = evaluate_day(date(2026, 1, 31), forecasts, actuals)
    assert report['delivery_date'] == '2026-02-01'
    assert report['metrics']['count'] == 1


def test_later_actual_publication_supersedes_earlier():
    forecasts = [sample_forecast('2026-01-02T00:00Z', '2026-01-01T08:30Z', 100)]
    actuals = [
        Actual(at('2026-01-02T00:00Z'), 130, at('2026-01-02T01:00Z')),
        Actual(at('2026-01-02T00:00Z'), 90, at('2026-01-03T01:00Z')),
        Actual(at('2026-01-02T00:30Z'), 90, at('2026-01-03T01:00Z')),
    ]
    report = evaluate_day(date(2026, 1, 1), forecasts, actuals)
    assert report['points'][0]['actual_mw'] == 90


def test_metrics_sign_and_percentiles():
    points = [
        {'error_mw': -10, 'forecast_mw': 100, 'actual_mw': 90, 'interval_minutes': 30},
        {'error_mw': 20, 'forecast_mw': 100, 'actual_mw': 120, 'interval_minutes': 30},
    ]
    value = metrics(points, 48)
    assert value['mae_mw'] == 15
    assert value['rmse_mw'] == round(sqrt(250), 2)
    assert value['bias_mw'] == 5
    assert value['shortfall_frequency_pct'] == 50
    assert value['shortfall_mwh'] == 5
    assert value['p90_abs_error_mw'] == 19
    assert value['coverage_pct'] == 4.17


def test_invalid_power_and_timestamps_are_rejected():
    for bad in [-1, float('nan'), float('inf'), True]:
        with pytest.raises((ValueError, TypeError)):
            power(bad)
    with pytest.raises(ValueError, match='Timezone missing'):
        timestamp('2026-01-15T09:00:00')


def test_parser_filters_non_wind_and_counts_invalid_rows():
    rows = [
        {'fuelType': 'GAS', 'startTime': '2026-01-02T00:00Z', 'generation': 999},
        {'fuelType': 'WIND', 'startTime': '2026-01-02T00:00Z', 'generation': 100},
        {'fuelType': 'WIND', 'startTime': '2026-01-02T00:30Z', 'generation': -1},
    ]
    actuals, invalid = parse_actuals(rows)
    assert len(actuals) == 1 and invalid == 1
    forecasts, invalid = parse_forecasts([{'publishTime': '2026-01-01T08:30Z', 'startTime': '2026-01-02T00:00Z', 'generation': 100}, {'startTime': 'x'}])
    assert len(forecasts) == 1 and invalid == 1


def test_london_cutoff_rejects_dates_outside_assignment():
    with pytest.raises(ValueError):
        decision_instant(date(2026, 2, 1))


def test_missing_outturn_preserves_forecast_profile_without_false_error():
    published = datetime(2026, 1, 15, 8, 30, tzinfo=timezone.utc)
    target = datetime(2026, 1, 16, 10, 0, tzinfo=timezone.utc)
    result = evaluate_day(date(2026, 1, 15), [Forecast(target, published, 2400)], [])
    assert result['selected_forecasts'] == 1
    assert result['missing_actual_intervals'] == 1
    assert result['points'] == []
    assert result['forecast_profile'][0]['forecast_mw'] == 2400
    assert result['forecast_profile'][0]['actual_mw'] is None
    assert result['metrics']['mae_mw'] is None


def test_single_forecast_defaults_to_hourly_instead_of_summing_two_actuals():
    target = at('2026-01-16T10:00Z')
    result = evaluate_day(date(2026, 1, 15),
        [Forecast(target, at('2026-01-15T08:30Z'), 180)],
        [Actual(target, 100), Actual(target + timedelta(minutes=30), 200)])
    assert result['resolution_minutes'] == 60
    assert result['resolution_inferred'] is False
    assert result['points'][0]['actual_mw'] == 150
    assert result['metrics']['shortfall_mwh'] == 30
