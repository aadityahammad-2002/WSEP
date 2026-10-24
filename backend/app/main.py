"""HTTP interface for day-ahead wind decision analytics."""
from __future__ import annotations

import csv
import io
import os
from contextlib import asynccontextmanager
from datetime import date, datetime, time, timedelta
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from .domain import FIRST_DECISION, LAST_DECISION, LONDON, UTC
from .service import WindService
from .predictions import PredictionStore, score_snapshot
from .history import build_history_page

service = WindService()
predictions = PredictionStore()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if os.getenv("AUTO_SYNC_ON_START", "0") == "1" and service.status()["available_days"] != 31:
        service.start_sync()
    yield


app = FastAPI(lifespan=lifespan, title="WindSight API", version="4.0.0", description="Historical replay and live UK day-ahead wind risk forecasts")
app.add_middleware(CORSMiddleware, allow_origins=[s.strip() for s in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")], allow_methods=["GET", "POST"], allow_headers=["*"])


def valid_day(day: date) -> date:
    if not FIRST_DECISION <= day <= LAST_DECISION:
        raise HTTPException(422, "Choose a decision date from 2026-01-01 to 2026-01-31")
    return day


def valid_history_day(day: date, *, future: bool = False) -> date:
    last = datetime.now(LONDON).date()
    if not date(2020, 1, 1) <= day <= last:
        raise HTTPException(422, f"Choose a decision date between 2020-01-01 and {last}")
    return day


@app.get("/api/analysis/day")
def analysis_day(day: date, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    return service.day(valid_history_day(day), hour, minute, allow_any_day=True)


@app.get("/api/analysis/intelligence")
def analysis_intelligence(day: date, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    return service.replay(valid_history_day(day), hour, minute)


@app.get("/api/analysis/versions")
def analysis_versions(day: date, start: str, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    try:
        return service.versions(valid_history_day(day), start, hour, minute)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/analysis/export.csv")
def analysis_export(day: date, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    report = service.replay(valid_history_day(day), hour, minute)
    if not report['profile']:
        raise HTTPException(409, "No Elexon forecasts are loaded for this date")
    output = io.StringIO()
    fields = ['start_time','publish_time','baseline_mw','engine_mw','actual_mw','error_mw','result','planning_buffer_mw','interval_minutes']
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for point in report['profile']:
        engine = point['adjusted_forecast_mw'] if point['adjusted_forecast_mw'] is not None else point['raw_forecast_mw']
        actual = point['actual_mw']
        error = round(actual-engine,2) if actual is not None else None
        lower = point['p10_actual_mw']
        reserve = round(max(engine-lower, 0),2) if lower is not None else None
        writer.writerow(dict(start_time=point['start_time'], publish_time=point['publish_time'],
                             baseline_mw=point['raw_forecast_mw'], engine_mw=engine,
                             actual_mw=actual, error_mw=error,
                             result='pending' if error is None else 'shortfall' if error < 0 else 'surplus',
                             planning_buffer_mw=reserve, interval_minutes=point['interval_minutes']))
    return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': f'attachment; filename="windsight-{day}.csv"'})


@app.get("/api/history")
def history(start: date, end: date, page: int = Query(1, ge=1),
            page_size: int = Query(5, ge=1, le=7), hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    valid_history_day(start)
    valid_history_day(end)
    if start > end:
        raise HTTPException(422, 'Start date must be on or before end date')
    if (end - start).days > 365:
        raise HTTPException(422, 'Select at most 366 days per range; use adjacent ranges for larger history')
    return build_history_page(service, start, end, page, page_size, hour, minute)


@app.post("/api/history/prepare", status_code=202)
def prepare_history(start: date, end: date, force: bool = False):
    valid_history_day(start)
    valid_history_day(end)
    if start > end or (end - start).days > 6:
        raise HTTPException(422, 'Import up to seven decision days at a time')
    started = service.start_range_sync(start, end, force=force)
    return {'started': started, **service.status()}


@app.get('/api/analysis/recent')
def analysis_recent(day: date, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    valid_history_day(day)
    days = [service.day(day - timedelta(days=n), hour, minute, allow_any_day=True) for n in range(13,-1,-1)]
    return {'daily': [{'decision_date': item['decision_date'], 'delivery_date': item['delivery_date'],
                       'available': item['available'], **item['metrics']} for item in days],
            'metrics': {'available_days': sum(bool(x['available']) for x in days), 'total_days': len(days)}}


@app.get("/api/health")
def health():
    return {"status": "ok", "version": "4.0.0"}


@app.get("/api/status")
def status():
    return service.status()


@app.post("/api/sync", status_code=202)
def sync(force: bool = False):
    return {"started": service.start_sync(force), **service.status()}


@app.get("/api/comparison")
def comparison(day: date = Query(default=date(2026, 1, 15)), hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    return service.day(valid_day(day), hour, minute)


@app.get("/api/metrics")
def monthly_metrics(hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    return service.month(hour, minute)


@app.get("/api/intelligence")
def intelligence(day: date = Query(default=date(2026, 1, 15)), hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    return service.intelligence(valid_day(day), hour, minute)


@app.get("/api/forecast-versions")
def forecast_versions(day: date, start: str, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    try:
        return service.versions(valid_day(day), start, hour, minute)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/export.csv")
def export(day: date = Query(default=date(2026, 1, 15)), hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    report = service.day(valid_day(day), hour, minute)
    if not report["available"]:
        raise HTTPException(409, "Elexon snapshots are not loaded for that date")
    buffer = io.StringIO()
    fields = ["start_time", "publish_time", "forecast_mw", "actual_mw", "error_mw", "absolute_error_mw", "shortfall_mw", "interval_minutes"]
    writer = csv.DictWriter(buffer, fieldnames=fields)
    writer.writeheader()
    writer.writerows(report["points"])
    return Response(buffer.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="windsight-{day}.csv"'})


@app.post('/api/prepare', status_code=202)
def prepare(day: date, force: bool = False):
    today = datetime.now(LONDON).date()
    if not date(2020, 1, 1) <= day <= today:
        raise HTTPException(422, 'Choose a UK decision date between 2020-01-01 and today')
    started = service.start_date_sync(day, force=force, include_actual=day < today)
    return {'started': started, 'day': str(day), **service.status()}


@app.get('/api/replay')
def replay(day: date, hour: int = Query(9, ge=0, le=23), minute: int = Query(50, ge=0, le=59)):
    if not date(2020, 1, 1) <= day < datetime.now(LONDON).date():
        raise HTTPException(422, 'Historical replay must use a past UK decision date')
    return service.replay(day, hour, minute)


@app.get('/api/live')
def live():
    now = datetime.now(UTC)
    today = now.astimezone(LONDON).date()
    report = service.replay(today, cutoff_override=now)
    gate = datetime.combine(today, time(9, 50), tzinfo=LONDON).astimezone(UTC)
    report['current_time'] = now.isoformat().replace('+00:00', 'Z')
    report['gate_closed'] = now > gate
    report['trading_note'] = 'After the 09:50 UK decision gate; newer forecasts are operational monitoring only.' if now > gate else 'Forecast as of now, before the 09:50 UK decision gate.'
    return report


@app.post('/api/live/snapshot', status_code=201)
def save_live_snapshot(cutoff: datetime | None = None):
    now = datetime.now(UTC)
    cutoff = cutoff or now
    if cutoff.tzinfo is None or not 0 <= (now - cutoff.astimezone(UTC)).total_seconds() <= 900:
        raise HTTPException(422, 'Supply an aware forecast cutoff within the last 15 minutes')
    if cutoff.astimezone(LONDON).date() != now.astimezone(LONDON).date():
        raise HTTPException(422, 'Forecast cutoff must be on the current UK decision day')
    report = service.replay(now.astimezone(LONDON).date(), cutoff_override=cutoff)
    if not report['profile']:
        raise HTTPException(409, 'No published delivery forecast loaded. Prepare/sync data before saving.')
    return predictions.save(report, now)


@app.get('/api/predictions')
def list_predictions():
    return {'items': predictions.list()}


@app.get('/api/predictions/{identity}')
def prediction(identity: str):
    snapshot = predictions.read(identity)
    if snapshot is None:
        raise HTTPException(404, 'Saved forecast not found')
    delivery = date.fromisoformat(snapshot['delivery_date'])
    actuals = service.store.read('actuals', delivery)
    return score_snapshot(snapshot, actuals)


@app.post('/api/predictions/{identity}/refresh-actual', status_code=202)
def refresh_prediction_actual(identity: str):
    snapshot = predictions.read(identity)
    if snapshot is None:
        raise HTTPException(404, 'Saved forecast not found')
    delivery = date.fromisoformat(snapshot['delivery_date'])
    if delivery > datetime.now(LONDON).date():
        raise HTTPException(409, 'Delivery date is in the future; actual data is not yet available')
    return {'started': service.start_outturn_sync(delivery), **service.status()}


# In the Docker image the React build is mounted behind FastAPI; source mode uses Vite.
static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="frontend")
