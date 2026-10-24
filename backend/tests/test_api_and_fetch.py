import asyncio
from datetime import date

import httpx
from fastapi.testclient import TestClient

from app.elexon import ElexonClient
from app.service import WindService
from app.store import SnapshotStore
import app.main as http_app


def test_elexon_queries_exactly_the_two_assignment_datasets():
    observed = []

    def handle(request: httpx.Request):
        observed.append(request)
        if 'WINDFOR' in str(request.url):
            return httpx.Response(200, json=[{'publishTime': '2026-01-15T08:30:00Z', 'startTime': '2026-01-16T09:00:00Z', 'generation': 1200}])
        return httpx.Response(200, json=[
            {'fuelType': 'WIND', 'settlementDate': '2026-01-16', 'startTime': '2026-01-16T09:00:00Z', 'generation': 1100},
            {'fuelType': 'GAS', 'settlementDate': '2026-01-16', 'startTime': '2026-01-16T09:00:00Z', 'generation': 800},
        ])

    client = ElexonClient(transport=httpx.MockTransport(handle))
    forecasts = asyncio.run(client.fetch('forecasts', date(2026, 1, 15)))
    actuals = asyncio.run(client.fetch('actuals', date(2026, 1, 16)))
    assert len(forecasts) == len(actuals) == 1
    assert '/datasets/WINDFOR/stream' in str(observed[0].url)
    assert observed[0].url.params['publishDateTimeFrom'] == '2026-01-15T00:00:00Z'
    assert observed[0].url.params['publishDateTimeTo'] == '2026-01-16T00:00:00Z'
    assert observed[1].url.params['settlementDateFrom'] == '2026-01-16'
    assert observed[1].url.params['settlementDateTo'] == '2026-01-17'
    assert observed[1].url.params['fuelType'] == 'WIND'


def test_snapshot_store_atomic_roundtrip(tmp_path):
    store = SnapshotStore(tmp_path)
    assert store.read('forecasts', date(2026, 1, 15)) is None
    rows = [{'startTime': '2026-01-16T09:00Z', 'generation': 1000}]
    store.write('forecasts', date(2026, 1, 15), rows)
    assert store.read('forecasts', date(2026, 1, 15)) == rows
    assert not list(tmp_path.rglob('*.tmp'))


def test_service_no_data_is_explicit(tmp_path):
    service = WindService(store=SnapshotStore(tmp_path))
    report = service.day(date(2026, 1, 15))
    assert report['available'] is False
    assert 'WINDFOR 2026-01-15' in report['missing']
    assert service.month()['metrics']['available_days'] == 0


def test_http_comparison_metrics_versions_and_csv(tmp_path, monkeypatch):
    store = SnapshotStore(tmp_path)
    store.write('forecasts', date(2026, 1, 14), [])
    store.write('forecasts', date(2026, 1, 15), [
        {'publishTime': '2026-01-15T08:30:00Z', 'startTime': '2026-01-16T09:00:00Z', 'generation': 1200},
        {'publishTime': '2026-01-15T10:30:00Z', 'startTime': '2026-01-16T09:00:00Z', 'generation': 1700},
    ])
    store.write('actuals', date(2026, 1, 16), [
        {'fuelType': 'WIND', 'startTime': '2026-01-16T09:00:00Z', 'settlementDate': '2026-01-16', 'generation': 1000},
        {'fuelType': 'WIND', 'startTime': '2026-01-16T09:30:00Z', 'settlementDate': '2026-01-16', 'generation': 1000},
    ])
    monkeypatch.setattr(http_app, 'service', WindService(store=store))
    client = TestClient(http_app.app)
    assert client.get('/api/health').json()['status'] == 'ok'
    data = client.get('/api/comparison?day=2026-01-15').json()
    assert data['available'] is True
    assert data['metrics']['mae_mw'] == 200
    assert data['points'][0]['forecast_mw'] == 1200
    summary = client.get('/api/metrics').json()
    assert summary['metrics']['available_days'] == 1
    assert summary['complete'] is False
    versions = client.get('/api/forecast-versions', params={'day':'2026-01-15', 'start':'2026-01-16T09:00:00Z'}).json()['versions']
    assert [v['eligible'] for v in versions] == [True, False]
    csv = client.get('/api/export.csv?day=2026-01-15')
    assert csv.status_code == 200 and '1200' in csv.text
    assert 'start_time,publish_time,forecast_mw' in csv.text
    assert client.get('/api/comparison?day=2026-02-15').status_code == 422
    assert client.get('/api/export.csv?day=2026-01-14').status_code == 409


def test_fallback_uses_yesterdays_forecast_if_morning_revision_is_too_late(tmp_path):
    store = SnapshotStore(tmp_path)
    store.write('forecasts', date(2026, 1, 14), [
        {'startTime':'2026-01-16T09:00:00Z','publishTime':'2026-01-14T23:30:00Z','generation':1500},
    ])
    store.write('forecasts', date(2026, 1, 15), [
        {'startTime':'2026-01-16T09:00:00Z','publishTime':'2026-01-15T10:30:00Z','generation':1800},
    ])
    store.write('actuals', date(2026, 1, 16), [
        {'fuelType':'WIND','settlementDate':'2026-01-16','startTime':'2026-01-16T09:00:00Z','generation':1400},
        {'fuelType':'WIND','settlementDate':'2026-01-16','startTime':'2026-01-16T09:30:00Z','generation':1400},
    ])
    report = WindService(store=store).day(date(2026, 1, 15))
    assert report['points'][0]['forecast_mw'] == 1500
    assert report['points'][0]['error_mw'] == -100


def test_complete_sync_uses_exactly_63_day_partitions(tmp_path):
    class TestElexon:
        async def fetch(self, kind: str, day: date):
            if kind == 'forecasts':
                return [{'startTime': str(day) + 'T12:00:00Z', 'publishTime': str(day) + 'T08:30:00Z', 'generation': 1000}]
            return [{'fuelType': 'WIND', 'settlementDate': str(day), 'startTime': str(day) + 'T12:00:00Z', 'generation': 1000}]

    service = WindService(store=SnapshotStore(tmp_path), client=TestElexon())
    asyncio.run(service.sync())
    status = service.status()
    assert status['sync_total'] == 63
    assert status['sync_done'] == 63
    assert status['available_days'] == 31
    assert status['errors'] == []
    assert service.store.path('forecasts', date(2025,12,31)).exists()
    assert service.store.path('actuals', date(2026,2,1)).exists()


def test_missing_actual_source_does_not_erase_known_forecast(tmp_path):
    store = SnapshotStore(tmp_path)
    store.write('forecasts', date(2026, 1, 14), [])
    store.write('forecasts', date(2026, 1, 15), [
        {'startTime':'2026-01-16T10:00:00Z','publishTime':'2026-01-15T08:30:00Z','generation':1500},
    ])
    result = WindService(store=store).day(date(2026, 1, 15))
    assert not result['available']
    assert result['missing'] == ['FUELHH 2026-01-16']
    assert len(result['forecast_profile']) == 1
    assert result['metrics']['count'] == 0
