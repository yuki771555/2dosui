from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.9/3.10 fallback
    tomllib = None


@dataclass(frozen=True)
class RuntimeConfig:
    sample_interval_sec: float = 1.0
    body_weight_kg: float = 60.0
    log_path: str = "logs/bed_log.csv"


@dataclass(frozen=True)
class ThresholdConfig:
    exit_ratio: float = 0.30
    return_ratio: float = 0.40
    monitor_sec: int = 1800
    confirm_sec: int = 180


@dataclass(frozen=True)
class Hx711Config:
    dout_pin: int = 5
    sck_pin: int = 6
    readings: int = 10
    zero_offset: float = 0.0
    scale_factor: float = 1.0


@dataclass(frozen=True)
class BuzzerConfig:
    enabled: bool = False
    pin: int = 18
    duration_sec: float = 3.0


@dataclass(frozen=True)
class DiscordConfig:
    enabled: bool = True
    mention: str = ""


@dataclass(frozen=True)
class AppConfig:
    runtime: RuntimeConfig
    thresholds: ThresholdConfig
    hx711: Hx711Config
    buzzer: BuzzerConfig
    discord: DiscordConfig


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    if tomllib is None:
        raise RuntimeError("Python 3.11+ is recommended for TOML config support.")
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(path: str | Path = "config.toml") -> AppConfig:
    data = _load_toml(Path(path))
    runtime = RuntimeConfig(**{**RuntimeConfig().__dict__, **data.get("runtime", {})})
    thresholds = ThresholdConfig(**{**ThresholdConfig().__dict__, **data.get("thresholds", {})})
    hx711 = Hx711Config(**{**Hx711Config().__dict__, **data.get("hx711", {})})
    buzzer = BuzzerConfig(**{**BuzzerConfig().__dict__, **data.get("buzzer", {})})
    discord = DiscordConfig(**{**DiscordConfig().__dict__, **data.get("discord", {})})
    return AppConfig(runtime, thresholds, hx711, buzzer, discord)


def load_env(path: str | Path = ".env") -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        return {}
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def ensure_default_config(path: str | Path = "config.toml") -> Path:
    target = Path(path)
    if target.exists():
        return target
    example = Path("config.toml.example")
    if example.exists():
        target.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
        return target
    target.write_text(render_config(load_config(Path("__missing__"))), encoding="utf-8")
    return target


def render_config(config: AppConfig) -> str:
    return f"""[runtime]
sample_interval_sec = {config.runtime.sample_interval_sec}
body_weight_kg = {config.runtime.body_weight_kg}
log_path = "{config.runtime.log_path}"

[thresholds]
exit_ratio = {config.thresholds.exit_ratio}
return_ratio = {config.thresholds.return_ratio}
monitor_sec = {config.thresholds.monitor_sec}
confirm_sec = {config.thresholds.confirm_sec}

[hx711]
dout_pin = {config.hx711.dout_pin}
sck_pin = {config.hx711.sck_pin}
readings = {config.hx711.readings}
zero_offset = {config.hx711.zero_offset}
scale_factor = {config.hx711.scale_factor}

[buzzer]
enabled = {str(config.buzzer.enabled).lower()}
pin = {config.buzzer.pin}
duration_sec = {config.buzzer.duration_sec}

[discord]
enabled = {str(config.discord.enabled).lower()}
mention = "{config.discord.mention}"
"""


def save_calibration(
    path: str | Path,
    *,
    zero_offset: float | None = None,
    scale_factor: float | None = None,
) -> None:
    cfg = load_config(path)
    hx = Hx711Config(
        dout_pin=cfg.hx711.dout_pin,
        sck_pin=cfg.hx711.sck_pin,
        readings=cfg.hx711.readings,
        zero_offset=cfg.hx711.zero_offset if zero_offset is None else zero_offset,
        scale_factor=cfg.hx711.scale_factor if scale_factor is None else scale_factor,
    )
    updated = AppConfig(cfg.runtime, cfg.thresholds, hx, cfg.buzzer, cfg.discord)
    Path(path).write_text(render_config(updated), encoding="utf-8")
