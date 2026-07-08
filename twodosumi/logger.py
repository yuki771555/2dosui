from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class LogRow:
    timestamp: datetime
    raw: float
    weight_kg: float
    smoothed_weight_kg: float
    state: str
    event: str


class CsvLogger:
    header = ["timestamp", "raw", "weight_kg", "smoothed_weight_kg", "state", "event"]

    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", newline="", encoding="utf-8")
        self._writer = csv.writer(self._file)
        if self.path.stat().st_size == 0:
            self._writer.writerow(self.header)
            self._file.flush()

    def write(self, row: LogRow) -> None:
        self._writer.writerow(
            [
                row.timestamp.isoformat(timespec="seconds"),
                f"{row.raw:.3f}",
                f"{row.weight_kg:.3f}",
                f"{row.smoothed_weight_kg:.3f}",
                row.state,
                row.event,
            ]
        )
        self._file.flush()

    def close(self) -> None:
        self._file.close()

    def __enter__(self) -> "CsvLogger":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

