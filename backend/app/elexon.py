"""Fetch original Elexon data using publication and settlement-date filters."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta

import httpx

BASE = "https://data.elexon.co.uk/bmrs/api/v1"


class ElexonError(RuntimeError):
    pass


class ElexonClient:
    def __init__(self, base_url: str = BASE, transport: httpx.AsyncBaseTransport | None = None):
        self.base_url = base_url.rstrip("/")
        self.transport = transport

    async def get(self, client: httpx.AsyncClient, path: str, params: dict) -> list[dict]:
        for attempt in range(4):
            try:
                response = await client.get(path, params=params)
                if response.status_code in (429, 500, 502, 503, 504):
                    response.raise_for_status()
                response.raise_for_status()
                data = response.json()
                rows = data["data"] if isinstance(data, dict) else data
                if not isinstance(rows, list):
                    raise ElexonError(f"Unexpected JSON body from {path}")
                return rows
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                if attempt == 3 or (isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code not in (429, 500, 502, 503, 504)):
                    raise ElexonError(f"Elexon request failed for {path}: {exc}") from exc
                await asyncio.sleep(0.4 * (2 ** attempt))
        raise AssertionError("Unreachable")

    async def fetch(self, kind: str, day: date) -> list[dict]:
        next_day = day + timedelta(days=1)
        if kind == "forecasts":
            # WINDFOR dataset filters refer to publication date, not delivery date.
            params = {"publishDateTimeFrom": f"{day}T00:00:00Z", "publishDateTimeTo": f"{next_day}T00:00:00Z"}
            path = "/datasets/WINDFOR/stream"
        elif kind == "actuals":
            params = {"settlementDateFrom": day.isoformat(), "settlementDateTo": next_day.isoformat(), "fuelType": "WIND"}
            path = "/datasets/FUELHH/stream"
        else:
            raise ValueError("Unknown kind")
        async with httpx.AsyncClient(base_url=self.base_url, timeout=30, transport=self.transport, headers={"Accept": "application/json"}) as client:
            rows = await self.get(client, path, params)
        if kind == "forecasts":
            # One published batch can forecast several delivery dates; keep its full history.
            rows = [r for r in rows if r.get("startTime") and r.get("publishTime")]
        else:
            rows = [r for r in rows if r.get("fuelType") == "WIND" and r.get("settlementDate") == day.isoformat()]
        return rows
