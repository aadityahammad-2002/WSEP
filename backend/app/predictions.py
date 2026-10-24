"""Immutable live forecast snapshots and post-delivery scoring."""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from math import sqrt

from .domain import LONDON, UTC, parse_actuals, timestamp


class PredictionStore:
    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else Path(__file__).resolve().parents[1] / 'data' / 'predictions'

    def save(self, report: dict, issued: datetime) -> dict:
        if issued.tzinfo is None:
            raise ValueError('Prediction timestamp must be aware')
        if report.get('mode') != 'live':
            raise ValueError('Only a live run can be stored as an issued forecast')
        if not report.get('profile'):
            raise ValueError('Cannot save a prediction without source forecast intervals')
        record = {
            'id': uuid.uuid4().hex,
            'created_at': issued.astimezone(UTC).isoformat().replace('+00:00', 'Z'),
            'decision_date': report['decision_date'],
            'delivery_date': report['delivery_date'],
            'cutoff_time': report['cutoff_time'],
            'model_version': 'residual-scenario-v1',
            'training': report['training'],
            'backtest': report['backtest'],
            'summary': report['summary'],
            'signals': report['signals'],
            'profile': [
                {**{k: v for k, v in point.items() if k != 'actual_mw'},
                 'prediction_mw': point['adjusted_forecast_mw'] if point['adjusted_forecast_mw'] is not None else point['raw_forecast_mw']}
                for point in report['profile']
            ],
        }
        self.root.mkdir(parents=True, exist_ok=True)
        path = self.root / f"{record['id']}.json"
        temp = path.with_suffix('.tmp')
        temp.write_text(json.dumps(record, separators=(',', ':')), encoding='utf-8')
        os.replace(temp, path)
        return record

    def read(self, identity: str) -> dict | None:
        if len(identity) != 32 or any(c not in '0123456789abcdef' for c in identity):
            return None
        path = self.root / f'{identity}.json'
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None

    def list(self, limit: int = 30) -> list[dict]:
        if not self.root.is_dir():
            return []
        files = sorted(self.root.glob('*.json'), reverse=True)
        items = [json.loads(path.read_text(encoding='utf-8')) for path in files]
        return sorted([{
            'id': item['id'], 'created_at': item['created_at'],
            'decision_date': item['decision_date'], 'delivery_date': item['delivery_date'],
            'interval_count': len(item['profile']),
        } for item in items], key=lambda x: x['created_at'], reverse=True)[:limit]


def score_snapshot(snapshot: dict, raw_actuals: list[dict] | None, now: datetime | None = None) -> dict:
    """Score frozen point forecasts, never a newly recomputed model prediction."""
    now = (now or datetime.now(UTC)).astimezone(UTC)
    actuals, invalid = parse_actuals(raw_actuals or [])
    by_start = {}
    for value in actuals:
        if value.published and value.published > now:
            continue
        previous = by_start.get(value.start)
        if previous is None or (value.published or datetime.min.replace(tzinfo=UTC)) > (previous.published or datetime.min.replace(tzinfo=UTC)):
            by_start[value.start] = value
    rows = []
    for point in snapshot['profile']:
        start = timestamp(point['start_time'])
        minutes = point['interval_minutes']
        interval_complete = start + timedelta(minutes=minutes) <= now
        samples = [by_start.get(start + timedelta(minutes=30 * offset)) for offset in range(minutes // 30)] if interval_complete else []
        observed = mean(item.mw for item in samples) if samples and all(s is not None for s in samples) else None
        prediction = point['prediction_mw']
        rows.append({
            **point, 'actual_mw': round(observed, 2) if observed is not None else None,
            'raw_error_mw': round(observed - point['raw_forecast_mw'], 2) if observed is not None else None,
            'prediction_error_mw': round(observed - prediction, 2) if observed is not None else None,
        })
    scored = [point for point in rows if point['actual_mw'] is not None]
    def aggregate(field: str):
        errors = [point[field] for point in scored]
        return {'mae_mw': round(mean(abs(x) for x in errors), 2),
                'rmse_mw': round(sqrt(mean(x*x for x in errors)), 2),
                'bias_mw': round(mean(errors), 2)} if errors else {'mae_mw': None, 'rmse_mw': None, 'bias_mw': None}
    expected = len(rows)
    return {
        **{k: v for k, v in snapshot.items() if k != 'profile'},
        'profile': rows, 'comparison': {
            'state': 'awaiting_actuals' if not scored else 'complete' if len(scored) == expected else 'partial',
            'matched_intervals': len(scored), 'forecast_intervals': expected,
            'actual_source_loaded': raw_actuals is not None, 'invalid_actual_rows': invalid,
            'baseline': aggregate('raw_error_mw'),
            'engine': aggregate('prediction_error_mw'),
        },
    }
