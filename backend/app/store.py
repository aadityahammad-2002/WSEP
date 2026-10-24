"""Small immutable day-partitioned source snapshots, suitable for a historical pilot."""
from __future__ import annotations

import json
import os
from functools import lru_cache
from datetime import date
from pathlib import Path

DEFAULT_ROOT = Path(os.getenv("WINDSIGHT_DATA_DIR", str(Path(__file__).resolve().parents[1] / "data"))) / "raw"


@lru_cache(maxsize=192)
def _load_snapshot(path: str, modified_ns: int, size: int) -> list[dict]:
    document = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(document, list):
        raise ValueError(f'Invalid snapshot: {path}')
    return document


class SnapshotStore:
    def __init__(self, root: Path | str = DEFAULT_ROOT):
        self.root = Path(root)

    def path(self, kind: str, day: date) -> Path:
        if kind not in {"forecasts", "actuals"}:
            raise ValueError("Unknown snapshot kind")
        return self.root / kind / f"{day.isoformat()}.json"

    def read(self, kind: str, day: date) -> list[dict] | None:
        path = self.path(kind, day)
        try:
            stat = path.stat()
        except FileNotFoundError:
            return None
        # Atomic snapshot replacement changes the file signature and invalidates the cache.
        return _load_snapshot(str(path), stat.st_mtime_ns, stat.st_size)

    def write(self, kind: str, day: date, rows: list[dict]) -> None:
        target = self.path(kind, day)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(rows, separators=(",", ":")), encoding="utf-8")
        os.replace(temporary, target)
