from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any


@dataclass
class AppConfig:
    reader: str
    log_path: str
    status_path: str = "logs/status.json"
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
    hx711_ready_timeout_sec: float = 3.0
    webhook_enabled: bool = False
    webhook_events: list[str] = field(default_factory=lambda: ["second_sleep_detected"])
    webhook_payload_format: str = "discord"
    webhook_timeout_sec: float = 5.0
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


KNOWN_EVENTS = {
    "left_bed",
    "returned",
    "return_cancelled",
    "second_sleep_detected",
    "monitor_done",
}


@dataclass
class Secrets:
    webhook_url: str = ""
    web_ui_token: str = ""


def load_secrets(path: str | Path | None) -> Secrets:
    if not path:
        return Secrets()
    target = Path(path)
    if not target.exists():
        return Secrets()
    with target.open("r", encoding="utf-8") as f:
        data: dict[str, Any] = json.load(f)
    return Secrets(**data)


def save_secrets(path: str | Path, secrets: Secrets) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(asdict(secrets), f, indent=2)
        f.write("\n")


def validate_config(config: AppConfig) -> list[str]:
    errors: list[str] = []
    if config.person_weight_kg <= 0:
        errors.append("person_weight_kg must be greater than 0")
    if not 0 <= config.exit_ratio < config.return_ratio <= 1:
        errors.append("exit_ratio and return_ratio must satisfy 0 <= exit < return <= 1")
    if config.sample_interval_sec <= 0:
        errors.append("sample_interval_sec must be greater than 0")
    if config.warmup_samples < 0:
        errors.append("warmup_samples must be 0 or greater")
    if config.median_samples <= 0:
        errors.append("median_samples must be greater than 0")
    if config.moving_average_window <= 0:
        errors.append("moving_average_window must be greater than 0")
    if config.monitor_sec <= 0:
        errors.append("monitor_sec must be greater than 0")
    if config.confirm_sec <= 0:
        errors.append("confirm_sec must be greater than 0")
    if config.hx711_ready_timeout_sec <= 0:
        errors.append("hx711_ready_timeout_sec must be greater than 0")
    if config.webhook_timeout_sec <= 0:
        errors.append("webhook_timeout_sec must be greater than 0")
    if config.webhook_payload_format not in {"discord", "json"}:
        errors.append("webhook_payload_format must be 'discord' or 'json'")
    unknown_events = sorted(set(config.webhook_events) - KNOWN_EVENTS)
    if unknown_events:
        errors.append(f"unknown webhook_events: {', '.join(unknown_events)}")
    return errors
