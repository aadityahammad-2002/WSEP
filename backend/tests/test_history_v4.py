"""History summaries use fixed pre-delivery buffers and separately score actuals."""
from datetime import date, timedelta

from fastapi.testclient import TestClient

from app.history import build_history_page
from app.service import WindService
from app.store import SnapshotStore


class ReplayStub:
    def replay(self, day, hour, minute):
        return {
            'delivery_date': str(day + timedelta(days=1)), 'cutoff_time': f'{day}T09:50:00Z',
            'status': 'ready', 'backtest': {'adjustment_enabled': False}, 'data_missing': [],
            'profile': [
                {'start_time': f'{day + timedelta(days=1)}T00:00:00Z', 'publish_time': f'{day}T08:00:00Z',
                 'interval_minutes': 60, 'raw_forecast_mw': 1000, 'adjusted_forecast_mw': None,
                 'actual_mw': 1300, 'p10_actual_mw': 800, 'risk_tier': 'watch'},
                {'start_time': f'{day + timedelta(days=1)}T01:00:00Z', 'publish_time': f'{day}T08:00:00Z',
                 'interval_minutes': 60, 'raw_forecast_mw': 1000, 'adjusted_forecast_mw': None,
                 'actual_mw': 700, 'p10_actual_mw': 850, 'risk_tier': 'watch'},
                {'start_time': f'{day + timedelta(days=1)}T02:00:00Z', 'publish_time': f'{day}T08:00:00Z',
                 'interval_minutes': 60, 'raw_forecast_mw': 1000, 'adjusted_forecast_mw': None,
                 'actual_mw': None, 'p10_actual_mw': None, 'risk_tier': 'unavailable'}
            ]
        }


def test_history_keeps_advance_reserve_when_wind_surpasses_forecast():
    day = date(2026, 9, 10)
    result = build_history_page(ReplayStub(), day, day, 1, 5, 9, 50)
    report = result['days'][0]
    high = report['intervals'][0]
    assert high['result'] == 'surplus' and high['error_mw'] == 300
    assert high['planning_buffer_mw'] == 200
    assert high['observed_shortfall_mwh'] == 0
    low = report['intervals'][1]
    assert low['result'] == 'shortfall' and low['error_mw'] == -300
    assert low['planning_buffer_mw'] == 150
    assert low['observed_shortfall_mwh'] == 300
    assert report['planned_buffer_mwh'] == 350
    assert report['scored_intervals'] == 2
    assert report['intervals'][2]['planning_buffer_mw'] is None
    assert report['intervals'][2]['result'] == 'pending'


def test_history_pages_preserve_range_and_bounded_page_size():
    start = date(2026, 9, 1)
    end = date(2026, 9, 12)
    result = build_history_page(ReplayStub(), start, end, 2, 5, 9, 50)
    assert result['total_days'] == 12
    assert result['total_pages'] == 3
    assert [row['decision_date'] for row in result['days']] == ['2026-09-07','2026-09-06','2026-09-05','2026-09-04','2026-09-03']


def test_new_routes_are_historical_and_do_not_fabricate_missing_records(tmp_path, monkeypatch):
    from app import main as api
    service = WindService(SnapshotStore(tmp_path / 'raw'))
    monkeypatch.setattr(api, 'service', service)
    client = TestClient(api.app)
    assert client.get('/api/history?start=2026-09-10&end=2026-09-09').status_code == 422
    assert client.get('/api/history?start=2026-01-01&end=2026-01-04&page_size=9').status_code == 422
    report = client.get('/api/history?start=2026-09-09&end=2026-09-10&page_size=1').json()
    assert report['days'][0]['forecast_intervals'] == 0
    assert report['days'][0]['planned_buffer_mwh'] is None
    assert client.get('/api/analysis/day?day=2026-09-10').status_code == 200
    assert client.get('/api/analysis/intelligence?day=2026-09-10').json()['profile'] == []
    assert client.get('/api/analysis/recent?day=2026-09-10').json()['metrics']['total_days'] == 14


def test_source_cache_reloads_when_snapshot_changes(tmp_path):
    store = SnapshotStore(tmp_path)
    day = date(2026, 9, 10)
    store.write('forecasts', day, [{'generation': 10}])
    assert store.read('forecasts', day)[0]['generation'] == 10
    store.write('forecasts', day, [{'generation': 100}])
    assert store.read('forecasts', day)[0]['generation'] == 100
