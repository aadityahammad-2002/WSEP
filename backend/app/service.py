"""Coordinates snapshot loading, forecast comparisons and monthly rollups."""
from __future__ import annotations

import asyncio
import threading
from datetime import date, timedelta, datetime, timezone
from calendar import monthrange

from .domain import FIRST_DECISION, LAST_DECISION, LONDON, evaluate_day, metrics, parse_actuals, parse_forecasts, timestamp, versions_for, decision_instant
from .intelligence import analyse, backtest
from .elexon import ElexonClient
from .store import SnapshotStore


class WindService:
    def __init__(self, store: SnapshotStore | None = None, client: ElexonClient | None = None):
        self.store = store or SnapshotStore()
        self.client = client or ElexonClient()
        self.state_lock = threading.Lock()
        self.syncing = False
        self.sync_done = 0
        self.sync_total = 63
        self.sync_errors: list[str] = []

    def day(self, day: date, hour: int = 9, minute: int = 50, actual_as_of=None, *, allow_any_day: bool = False, cutoff_override=None) -> dict:
        source_today = self.store.read("forecasts", day)
        source_previous = self.store.read("forecasts", day - timedelta(days=1))
        source_actuals = self.store.read("actuals", day + timedelta(days=1))
        missing = []
        if source_today is None:
            missing.append(f"WINDFOR {day}")
        if source_previous is None:
            missing.append(f"WINDFOR {day - timedelta(days=1)}")
        if source_actuals is None:
            missing.append(f"FUELHH {day + timedelta(days=1)}")

        # Outturn and forecast import independently; a delayed outturn must not hide
        # a forecast that was already known at the historical decision cutoff.
        forecast_rows = (source_previous or []) + (source_today or [])
        forecasts, forecast_invalid = parse_forecasts(forecast_rows)
        actuals, actual_invalid = parse_actuals(source_actuals or [])
        result = evaluate_day(day, forecasts, actuals, hour, minute, actual_as_of, allow_any_day=allow_any_day, cutoff_override=cutoff_override)
        result.update({
            "available": not missing,
            "missing": missing,
            "invalid_records": forecast_invalid + actual_invalid,
            "source": "Elexon WINDFOR + FUELHH",
        })
        return result

    def month(self, hour: int = 9, minute: int = 50) -> dict:
        days = [self.day(FIRST_DECISION + timedelta(days=n), hour, minute) for n in range(31)]
        present = [x for x in days if x["available"]]
        observations = [p for d in present for p in d["points"]]
        expected = sum(x["metrics"]["expected"] for x in present)
        summary = metrics(observations, expected)
        summary["available_days"] = len(present)
        summary["total_days"] = 31
        summary["missing_days"] = [d["decision_date"] for d in days if not d["available"]]
        daily = [{
            "decision_date": d["decision_date"], "delivery_date": d["delivery_date"],
            "available": d["available"], **d["metrics"],
        } for d in days]
        return {"metrics": summary, "daily": daily, "complete": len(present) == 31}

    def calendar_month(self, selected: date, hour: int = 9, minute: int = 50) -> dict:
        """Aggregate each decision date in the selected calendar month (not just 14 days)."""
        days = [self.day(date(selected.year, selected.month, n), hour, minute, allow_any_day=True)
                for n in range(1, monthrange(selected.year, selected.month)[1] + 1)]
        present = [item for item in days if item['available']]
        observations = [point for item in present for point in item['points']]
        expected = sum(item['metrics']['expected'] for item in present)
        summary = metrics(observations, expected)
        summary.update({
            'available_days': len(present), 'total_days': len(days),
            'missing_days': [item['decision_date'] for item in days if not item['available']],
        })
        daily = [{'decision_date': item['decision_date'], 'delivery_date': item['delivery_date'],
                  'available': item['available'], **item['metrics']} for item in days]
        return {'metrics': summary, 'daily': daily, 'complete': len(present) == len(days)}

    def intelligence(self, day: date, hour: int = 9, minute: int = 50) -> dict:
        target = self.day(day, hour, minute)
        reports = {}
        for offset in range((day - FIRST_DECISION).days + 1):
            d = FIRST_DECISION + timedelta(days=offset)
            if d <= day - timedelta(days=2):
                reports[d] = self.day(d, hour, minute, actual_as_of=decision_instant(day, hour, minute))

        def training_before(target_day: date) -> list[dict]:
            as_of = decision_instant(target_day, hour, minute)
            earliest = max(FIRST_DECISION, target_day - timedelta(days=16))
            return [self.day(d, hour, minute, actual_as_of=as_of)
                    for d in sorted(reports)
                    if earliest <= d <= target_day - timedelta(days=2)]

        training = training_before(day)
        pairs = [(reports[d], training_before(d)) for d in sorted(reports)]
        return analyse(target, training, backtest(pairs))

    def versions(self, day: date, start: str, hour: int = 9, minute: int = 50) -> dict:
        today = self.store.read("forecasts", day)
        previous = self.store.read("forecasts", day - timedelta(days=1))
        if today is None or previous is None:
            return {"versions": [], "decision_date": str(day)}
        forecasts, _ = parse_forecasts(previous + today)
        return {"versions": versions_for(timestamp(start), forecasts, decision_instant(day, hour, minute)), "decision_date": str(day)}

    def status(self) -> dict:
        available = sum(
            self.store.path("forecasts", FIRST_DECISION + timedelta(days=n)).exists()
            and self.store.path("forecasts", FIRST_DECISION + timedelta(days=n - 1)).exists()
            and self.store.path("actuals", FIRST_DECISION + timedelta(days=n + 1)).exists()
            for n in range(31)
        )
        with self.state_lock:
            return {"available_days": available, "total_days": 31, "syncing": self.syncing,
                    "sync_done": self.sync_done, "sync_total": self.sync_total,
                    "errors": list(self.sync_errors), "source": "Elexon FUELHH / WINDFOR", "real_data_only": True}

    async def sync(self, force: bool = False, reserved: bool = False) -> None:
        with self.state_lock:
            if self.syncing and not reserved:
                return
            self.syncing, self.sync_done, self.sync_total, self.sync_errors = True, 0, 63, []
        jobs = [("forecasts", FIRST_DECISION + timedelta(days=n - 1)) for n in range(32)]
        jobs += [("actuals", FIRST_DECISION + timedelta(days=n + 1)) for n in range(31)]
        sem = asyncio.Semaphore(3)

        async def process(kind: str, day: date):
            async with sem:
                try:
                    if force or self.store.read(kind, day) is None:
                        records = await self.client.fetch(kind, day)
                        # Empty responses are not written as verified observations.
                        if not records:
                            raise ValueError("Elexon returned no usable records")
                        self.store.write(kind, day, records)
                except Exception as exc:
                    with self.state_lock:
                        self.sync_errors.append(f"{kind} {day}: {str(exc)[:220]}")
                finally:
                    with self.state_lock:
                        self.sync_done += 1
        try:
            await asyncio.gather(*(process(*job) for job in jobs))
        finally:
            with self.state_lock:
                self.syncing = False

    def start_sync(self, force: bool = False) -> bool:
        with self.state_lock:
            if self.syncing:
                return False
            # Reserve the lock before the worker thread begins.
            self.syncing = True
        def worker():
            asyncio.run(self.sync(force, reserved=True))
        threading.Thread(target=worker, daemon=True, name="elexon-sync").start()
        return True


    def replay(self, day: date, hour: int = 9, minute: int = 50, cutoff_override=None) -> dict:
        """Replay as-of forecasts; expose target outturn only for ex-post comparison."""
        cutoff = cutoff_override or decision_instant(day, hour, minute, allow_any_day=True)
        is_live = cutoff_override is not None
        target = self.day(day, hour, minute, actual_as_of=cutoff if is_live else None,
                          allow_any_day=True, cutoff_override=cutoff)
        cache: dict[tuple[date, datetime, bool], dict] = {}

        def historical(d: date, as_of: datetime, scoring: bool = False) -> dict:
            key = (d, as_of, scoring)
            if key not in cache:
                # Test-day actuals score a forecast after the fact. Earlier data used
                # to fit it must have existed before that historical decision.
                cache[key] = self.day(d, hour, minute,
                    actual_as_of=None if scoring else as_of, allow_any_day=True)
            return cache[key]

        def training_before(d: date, decision_cutoff: datetime) -> list[dict]:
            # Leave a full calendar-day gap after delivery for published outturns.
            return [historical(d - timedelta(days=n), decision_cutoff)
                    for n in range(2, 17)]

        training = training_before(day, cutoff)
        pairs = []
        for n in range(15, 1, -1):
            test_date = day - timedelta(days=n)
            test_cutoff = decision_instant(test_date, hour, minute, allow_any_day=True)
            pairs.append((historical(test_date, test_cutoff, scoring=True),
                          training_before(test_date, test_cutoff)))
        report = analyse(target, training, backtest(pairs))
        report['mode'] = 'live' if is_live else 'historical'
        report['data_missing'] = target['missing']
        report['source_forecast_count'] = target['selected_forecasts']
        report['time_travel_rule'] = 'Only forecasts published at or before each reconstructed cutoff; training cutoff also enforced separately for every backtest day.'
        report['training']['policy'] = 'Only decisions at least 2 UK calendar days before target; earlier walk-forward holdouts enforce their own historical cutoffs.'
        report['limitations'] = [x.replace('calibration is only within January 2026 and may be sparse', 'calibration is limited to imported prior decision days and may be sparse') for x in report['limitations']]
        return report

    async def sync_for_date(self, day: date, *, force: bool = False, include_actual: bool = True) -> None:
        """Fetch a rolling calibration window for replay or tomorrow's snapshot."""
        first = day - timedelta(days=32)
        forecast_days = [first - timedelta(days=1) + timedelta(days=n) for n in range(34)]
        actual_days = [first + timedelta(days=n+1) for n in range(33)] if include_actual else [first + timedelta(days=n+1) for n in range(32)]
        today = datetime.now(LONDON).date()
        actual_days = [d for d in actual_days if d <= today]
        jobs = [('forecasts', d) for d in forecast_days] + [('actuals', d) for d in actual_days]
        with self.state_lock:
            self.sync_done, self.sync_total, self.sync_errors = 0, len(jobs), []
        sem = asyncio.Semaphore(3)
        async def one(kind: str, d: date):
            async with sem:
                try:
                    refresh_current_publications = not include_actual and kind == 'forecasts' and d >= day - timedelta(days=1)
                    if force or refresh_current_publications or self.store.read(kind, d) is None:
                        records = await self.client.fetch(kind, d)
                        if not records:
                            raise ValueError('Elexon returned no usable records')
                        self.store.write(kind, d, records)
                except Exception as exc:
                    with self.state_lock:
                        self.sync_errors.append(f'{kind} {d}: {str(exc)[:220]}')
                finally:
                    with self.state_lock:
                        self.sync_done += 1
        try:
            await asyncio.gather(*(one(*job) for job in jobs))
        finally:
            with self.state_lock:
                self.syncing = False

    def start_date_sync(self, day: date, *, force: bool = False, include_actual: bool = True) -> bool:
        with self.state_lock:
            if self.syncing:
                return False
            self.syncing = True
        def worker():
            try:
                asyncio.run(self.sync_for_date(day, force=force, include_actual=include_actual))
            finally:
                with self.state_lock:
                    self.syncing = False
        threading.Thread(target=worker, daemon=True, name='rolling-elexon-sync').start()
        return True

    def start_outturn_sync(self, delivery: date) -> bool:
        with self.state_lock:
            if self.syncing:
                return False
            self.syncing, self.sync_done, self.sync_total, self.sync_errors = True, 0, 1, []
        def worker():
            async def fetch():
                try:
                    rows = await self.client.fetch('actuals', delivery)
                    if not rows:
                        raise ValueError('No actual WIND readings available for the delivery date')
                    self.store.write('actuals', delivery, rows)
                except Exception as exc:
                    with self.state_lock:
                        self.sync_errors.append(f'actuals {delivery}: {str(exc)[:220]}')
                finally:
                    with self.state_lock:
                        self.sync_done, self.syncing = 1, False
            asyncio.run(fetch())
        threading.Thread(target=worker, daemon=True, name='outturn-refresh').start()
        return True

    def start_range_sync(self, start: date, end: date, *, force: bool = False) -> bool:
        """Import the visible history page and its trailing calibration window."""
        with self.state_lock:
            if self.syncing:
                return False
            self.syncing = True
        def worker():
            # A shared window avoids importing the same calibration days repeatedly.
            earliest = start - timedelta(days=33)
            forecast_days = [earliest + timedelta(days=n) for n in range((end - earliest).days + 1)]
            actual_end = min(end + timedelta(days=1), datetime.now(LONDON).date())
            actual_days = [earliest + timedelta(days=n) for n in range((actual_end - earliest).days + 1)]
            jobs = [('forecasts', d) for d in forecast_days] + [('actuals', d) for d in actual_days]
            async def run():
                with self.state_lock:
                    self.sync_done, self.sync_total, self.sync_errors = 0, len(jobs), []
                sem = asyncio.Semaphore(4)
                async def get(kind, d):
                    async with sem:
                        try:
                            if force or self.store.read(kind, d) is None:
                                records = await self.client.fetch(kind, d)
                                if not records:
                                    raise ValueError('No usable Elexon observations')
                                self.store.write(kind, d, records)
                        except Exception as exc:
                            with self.state_lock:
                                self.sync_errors.append(f'{kind} {d}: {str(exc)[:180]}')
                        finally:
                            with self.state_lock:
                                self.sync_done += 1
                await asyncio.gather(*(get(kind, d) for kind, d in jobs))
            try:
                asyncio.run(run())
            finally:
                with self.state_lock:
                    self.syncing = False
        threading.Thread(target=worker, daemon=True, name='history-elexon-sync').start()
        return True
