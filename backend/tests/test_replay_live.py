"""Regression coverage for the replay and live prediction lifecycle."""
from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.domain import Forecast, Actual, evaluate_day, LONDON, UTC
from app.predictions import PredictionStore, score_snapshot
from app.service import WindService
from app.store import SnapshotStore


def stamp(value: str):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def test_replay_outside_january_selects_only_forecast_known_at_cutoff(tmp_path):
    store = SnapshotStore(tmp_path)
    day = date(2026, 9, 10)
    delivery = '2026-09-11T09:00:00Z'
    store.write('forecasts', day - timedelta(days=1), [
        {'startTime': delivery,'publishTime':'2026-09-09T21:00:00Z','generation':150},
    ])
    store.write('forecasts', day, [
        {'startTime': delivery,'publishTime':'2026-09-10T08:00:00Z','generation':180},
        {'startTime': delivery,'publishTime':'2026-09-10T11:00:00Z','generation':220},
    ])
    store.write('actuals', day + timedelta(days=1), [
        {'fuelType':'WIND','startTime':delivery,'generation':165},
        {'fuelType':'WIND','startTime':'2026-09-11T09:30:00Z','generation':175},
    ])
    report = WindService(store=store).replay(day, 9, 50)
    assert report['profile'][0]['raw_forecast_mw'] == 180
    # Scoring uses later measured output; model training never uses it.
    assert report['profile'][0]['actual_mw'] == 170
    assert report['profile'][0]['adjusted_forecast_mw'] is None
    assert report['training']['sample_intervals'] == 0


def test_uk_dst_end_expected_settlement_periods():
    # Day after the 2026-10-24 decision contains 25 hours in London.
    start = stamp('2026-10-24T08:00:00Z')
    f = [Forecast(stamp('2026-10-24T23:00:00Z'),start,800)]
    report = evaluate_day(date(2026,10,24), f, [], allow_any_day=True)
    assert report['metrics']['expected'] == 25
    # Spring transition similarly creates a 23-hour delivery day.
    report = evaluate_day(date(2026,3,28), [Forecast(stamp('2026-03-29T00:00:00Z'), stamp('2026-03-28T08:00:00Z'), 800)],[],allow_any_day=True)
    assert report['metrics']['expected'] == 23


def test_frozen_live_prediction_preserves_original_values(tmp_path):
    issued = stamp('2026-10-24T09:00:00Z')
    template = {
        'mode':'live','decision_date':'2026-10-24','delivery_date':'2026-10-25',
        'cutoff_time':'2026-10-24T09:00:00Z',
        'training':{'sample_intervals':30},'backtest':{'adjustment_enabled':False},
        'summary':{},'signals':[],
        'profile':[{'start_time':'2026-10-24T23:00:00Z',
                    'publish_time':'2026-10-24T08:00:00Z','raw_forecast_mw':900,
                    'adjusted_forecast_mw':None, 'interval_minutes':60,
                    'p10_actual_mw':700,'p90_actual_mw':1050,
                    'downside_buffer_mw':200,'risk_tier':'elevated','actual_mw':None}]
    }
    store = PredictionStore(tmp_path)
    saved = store.save(template,issued)
    template['profile'][0]['raw_forecast_mw']=5000
    frozen = store.read(saved['id'])
    assert frozen['profile'][0]['prediction_mw'] == 900
    assert frozen['profile'][0]['raw_forecast_mw'] == 900
    assert score_snapshot(frozen,None,stamp('2026-10-24T09:01:00Z'))['comparison']['state']=='awaiting_actuals'
    raw = [{'fuelType':'WIND','startTime':'2026-10-24T23:00:00Z','generation':810},
           {'fuelType':'WIND','startTime':'2026-10-24T23:30:00Z','generation':830}]
    result = score_snapshot(frozen,raw,stamp('2026-10-25T01:00:00Z'))
    assert result['comparison']['state']=='complete'
    assert result['comparison']['engine']['mae_mw']==80
    assert result['comparison']['baseline']['bias_mw']==-80
    assert result['profile'][0]['raw_forecast_mw']==900


def test_outturn_not_scored_until_interval_finishes(tmp_path):
    template = {'mode':'live','decision_date':'2026-10-24','delivery_date':'2026-10-25',
                'cutoff_time':'2026-10-24T08:00:00Z','training':{},'backtest':{},'summary':{},'signals':[],
                'profile':[{'start_time':'2026-10-24T23:00:00Z','raw_forecast_mw':400,'interval_minutes':60,
                            'adjusted_forecast_mw':None,'actual_mw':None}]}
    snapshot=PredictionStore(tmp_path).save(template,stamp('2026-10-24T08:00:00Z'))
    actuals=[{'fuelType':'WIND','startTime':'2026-10-24T23:00:00Z','generation':500},
             {'fuelType':'WIND','startTime':'2026-10-24T23:30:00Z','generation':500}]
    result=score_snapshot(snapshot,actuals,stamp('2026-10-24T23:45:00Z'))
    assert result['comparison']['matched_intervals']==0
    result=score_snapshot(snapshot,actuals,stamp('2026-10-25T00:00:00Z'))
    assert result['comparison']['matched_intervals']==1


def test_prediction_path_is_validated(tmp_path):
    store=PredictionStore(tmp_path)
    assert store.read('../secret') is None
    assert store.list()==[]


def test_new_http_routes_do_not_generate_fake_data(tmp_path, monkeypatch):
    import app.main as http_app
    replacement = WindService(SnapshotStore(tmp_path / 'raw'))
    monkeypatch.setattr(http_app, 'service', replacement)
    monkeypatch.setattr(http_app, 'predictions', PredictionStore(tmp_path / 'saved'))
    client = TestClient(http_app.app)
    assert client.get('/api/live').status_code == 200
    today = datetime.now(LONDON).date()
    prior = today - timedelta(days=5)
    history = client.get(f'/api/replay?day={prior}')
    assert history.status_code == 200
    assert history.json()['profile'] == []
    assert client.post('/api/live/snapshot').status_code == 409
    assert client.get('/api/predictions').json() == {'items': []}
    assert client.get('/api/predictions/bad-path').status_code == 404
    assert client.get(f'/api/replay?day={today}').status_code == 422
