"""Range reports keep ex-ante wind planning separate from ex-post settlement."""
from __future__ import annotations

from datetime import date, timedelta
from statistics import mean


def build_history_page(service, start: date, end: date, page: int, page_size: int, hour: int, minute: int) -> dict:
    total = (end - start).days + 1
    newest = end - timedelta(days=(page - 1) * page_size)
    oldest = max(start, newest - timedelta(days=page_size - 1))
    if newest < start:
        return {"start": str(start), "end": str(end), "page": page, "page_size": page_size,
                "total_days": total, "total_pages": (total + page_size - 1) // page_size, "days": []}
    days = []
    for i in range((newest - oldest).days + 1):
        day = newest - timedelta(days=i)
        report = service.replay(day, hour, minute)
        intervals = []
        for point in report['profile']:
            predicted = point['adjusted_forecast_mw'] if point['adjusted_forecast_mw'] is not None else point['raw_forecast_mw']
            measured = point['actual_mw']
            # This scenario buffer is fixed at prediction time. Later surplus never removes it.
            lower = point['p10_actual_mw']
            reserve = round(max(predicted - lower, 0), 2) if lower is not None else None
            duration = point['interval_minutes'] / 60
            error = round(measured - predicted, 2) if measured is not None else None
            intervals.append({
                'start_time': point['start_time'], 'publish_time': point['publish_time'],
                'interval_minutes': point['interval_minutes'], 'baseline_mw': point['raw_forecast_mw'],
                'predicted_mw': round(predicted, 2), 'actual_mw': measured, 'error_mw': error,
                'result': 'shortfall' if error is not None and error < 0 else 'surplus' if error is not None else 'pending',
                'planning_buffer_mw': reserve,
                'planning_buffer_mwh': round(reserve * duration, 2) if reserve is not None else None,
                'observed_shortfall_mwh': round(max(-error, 0) * duration, 2) if error is not None else None,
                'risk_tier': point['risk_tier'],
            })
        scored = [x for x in intervals if x['error_mw'] is not None]
        errors = [x['error_mw'] for x in scored]
        buffers = [x for x in intervals if x['planning_buffer_mwh'] is not None]
        days.append({
            'decision_date': day.isoformat(), 'delivery_date': report['delivery_date'],
            'cutoff_time': report['cutoff_time'], 'model_status': report['status'],
            'adjustment_enabled': report['backtest']['adjustment_enabled'],
            'forecast_intervals': len(intervals), 'scored_intervals': len(scored),
            'risk_coverage_intervals': len(buffers), 'mean_prediction_mw': round(mean(x['predicted_mw'] for x in intervals), 2) if intervals else None,
            'mean_actual_mw': round(mean(x['actual_mw'] for x in scored), 2) if scored else None,
            'mae_mw': round(mean(abs(e) for e in errors), 2) if errors else None,
            'bias_mw': round(mean(errors), 2) if errors else None,
            'planned_buffer_mwh': round(sum(x['planning_buffer_mwh'] for x in buffers), 2) if buffers else None,
            'observed_shortfall_mwh': round(sum(x['observed_shortfall_mwh'] for x in scored), 2) if scored else None,
            'shortfall_intervals': sum(x['result'] == 'shortfall' for x in scored),
            'surplus_intervals': sum(x['result'] == 'surplus' for x in scored),
            'missing': report['data_missing'], 'intervals': intervals,
        })
    return {"start": str(start), "end": str(end), "page": page, "page_size": page_size,
            "total_days": total, "total_pages": (total + page_size - 1) // page_size, "days": days,
            "planning_note": "Scenario reserve is wind-side uncertainty, NOT a required electricity purchase. It is fixed before actual generation is observed."}
