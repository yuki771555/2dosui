from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
import json
import os
from pathlib import Path


@dataclass
class RuntimeStatus:
    timestamp: str
    pid: int
    running: bool
    raw: float | None = None
    weight_kg: float | None = None
    smoothed_weight_kg: float | None = None
    state: str = ""
    event: str = ""
    message: str = ""
    next_scheduled_alarm: dict[str, object] | None = None
    pending_rechecks: list[dict[str, object]] | None = None


def make_status(
    *,
    raw: float | None = None,
    weight_kg: float | None = None,
    smoothed_weight_kg: float | None = None,
    state: str = "",
    event: str = "",
    message: str = "",
    running: bool = True,
    next_scheduled_alarm: dict[str, object] | None = None,
    pending_rechecks: list[dict[str, object]] | None = None,
) -> RuntimeStatus:
    return RuntimeStatus(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        pid=os.getpid(),
        running=running,
        raw=raw,
        weight_kg=weight_kg,
        smoothed_weight_kg=smoothed_weight_kg,
        state=state,
        event=event,
        message=message,
        next_scheduled_alarm=next_scheduled_alarm,
        pending_rechecks=pending_rechecks,
    )


def write_status(path: str | Path, status: RuntimeStatus) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(asdict(status), f, indent=2)
        f.write("\n")
    tmp.replace(target)


def read_status(path: str | Path) -> dict[str, object]:
    target = Path(path)
    if not target.exists():
        return {"running": False, "message": "status file not found"}
    with target.open("r", encoding="utf-8") as f:
        return dict(json.load(f))
