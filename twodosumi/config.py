from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    reader: str
    log_path: str
    load_cell_layout: str = "four_half_bridge_aggregate"
    zero_offset: float = 0.0
    scale_factor: float = 1.0
    person_weight_kg: float = 60.0
    sample_interval_sec: float = 1.0
    warmup_samples: int = 5
    median_samples: int = 9
    moving_average_window: int = 5
    exit_ratio: float = 0.3
    return_ratio: float = 0.4
    monitor_sec: float = 1800.0
    confirm_sec: float = 180.0
    data_pin: str = "D5"
    clock_pin: str = "D6"
    mock_sequence: list[dict[str, float]] = field(default_factory=list)


FOUR_CELL_WIRING = {
    "E+": "LC1 + LC2",
    "E-": "LC3 + LC4",
    "A+": "LC1 + LC3",
    "A-": "LC2 + LC4",
}


def load_config(path: str | Path) -> AppConfig:
    with Path(path).open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return AppConfig(**data)


def save_config(path: str | Path, config: AppConfig) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(asdict(config), f, indent=2)
        f.write("\n")
