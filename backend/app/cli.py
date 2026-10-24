"""Historical Elexon import and pre-submission data checks."""
from __future__ import annotations

import argparse
import asyncio
from datetime import timedelta

from .domain import FIRST_DECISION
from .service import WindService


def verify(service: WindService) -> bool:
    status = service.status()
    missing = []
    sparse = []
    matched = 0
    invalid = 0
    for offset in range(31):
        report = service.day(FIRST_DECISION + timedelta(days=offset))
        if not report["available"]:
            missing.append(report["decision_date"])
        if report["available"] and report["metrics"]["count"] == 0:
            sparse.append(report["decision_date"])
        matched += report["metrics"]["count"]
        invalid += report["invalid_records"]

    print(f"Source coverage: {status['available_days']}/31 decision dates")
    print(f"Comparable intervals: {matched}")
    print(f"Rejected source rows: {invalid}")
    if missing:
        print(f"Missing source dates ({len(missing)}): {', '.join(missing)}")
    if sparse:
        print(f"Dates without matched intervals ({len(sparse)}): {', '.join(sparse)}")
    for error in status["errors"]:
        print(f"Source error: {error}")
    return not missing and not sparse and not status["errors"] and matched > 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Download or verify January 2026 Elexon wind observations")
    parser.add_argument("command", nargs="?", default="sync", choices=["sync", "verify"])
    parser.add_argument("--force", action="store_true", help="Replace cached source-day snapshots when syncing")
    args = parser.parse_args()
    service = WindService()
    if args.command == "sync":
        asyncio.run(service.sync(force=args.force))
    if not verify(service):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
