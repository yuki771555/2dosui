from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
import sys
import time

from .alarm import ALARM_EVENT, SecondSleepAlarm
from .config import FOUR_CELL_WIRING, AppConfig, load_config, load_secrets, save_config, validate_config
from .detector import SecondSleepDetector
from .logger import CsvLogger, LogRow
from .notifier import Notification, WebhookNotifier
from .sensors import create_reader, median_raw, moving_average, warmup
from .status import make_status, write_status


def _raw_to_weight(raw: float, config: AppConfig) -> float:
    if config.scale_factor == 0:
        raise ValueError("scale_factor must not be 0")
    return (raw - config.zero_offset) / config.scale_factor


def _print_wiring_summary(config: AppConfig) -> None:
    if config.load_cell_layout != "four_half_bridge_aggregate":
        print(f"layout={config.load_cell_layout}")
        return

    print("layout=four_half_bridge_aggregate")
    print("HX711 load cell bridge:")
    for terminal, cells in FOUR_CELL_WIRING.items():
        print(f"  {terminal}: {cells}")
    print(
        "HX711 to Raspberry Pi: "
        f"VCC=3.3V, GND=GND, DT/DOUT={config.data_pin}, SCK/CLK={config.clock_pin}"
    )


def calibrate_zero(args: argparse.Namespace) -> int:
    zero = calibrate_zero_file(args.config, args.samples)
    print(f"ZERO_OFFSET saved: {zero:.3f}")
    return 0


def calibrate_zero_file(config_path: str, samples: int) -> float:
    config = load_config(config_path)
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    _print_wiring_summary(config)
    reader = create_reader(config)
    warmup(reader, config.warmup_samples)
    zero = median_raw(reader, samples)
    config.zero_offset = zero
    save_config(config_path, config)
    return zero


def calibrate_scale_file(config_path: str, known_kg: float, samples: int) -> float:
    if known_kg <= 0:
        raise ValueError("known_kg must be greater than 0")
    config = load_config(config_path)
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    _print_wiring_summary(config)
    reader = create_reader(config)
    warmup(reader, config.warmup_samples)
    raw = median_raw(reader, samples)
    config.scale_factor = (raw - config.zero_offset) / known_kg
    save_config(config_path, config)
    return config.scale_factor


def calibrate_scale(args: argparse.Namespace) -> int:
    scale = calibrate_scale_file(args.config, args.known_kg, args.samples)
    print(f"SCALE_FACTOR saved: {scale:.6f}")
    return 0


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    errors = validate_config(config)
    if errors:
        raise ValueError("; ".join(errors))
    secrets = load_secrets(args.secrets)
    notifier = WebhookNotifier(config, secrets)
    alarm = SecondSleepAlarm(config, secrets)
    _print_wiring_summary(config)
    reader = create_reader(config)
    detector = SecondSleepDetector(config)
    weights: deque[float] = deque(maxlen=max(1, config.moving_average_window))

    warmup(reader, config.warmup_samples)
    started = time.monotonic()
    sample_count = 0

    try:
        with CsvLogger(config.log_path) as logger, alarm:
            while args.max_samples is None or sample_count < args.max_samples:
                loop_started = time.monotonic()
                raw = median_raw(reader, config.median_samples)
                weight = _raw_to_weight(raw, config)
                weights.append(weight)
                smoothed = moving_average(weights)
                result = detector.update(smoothed, time.monotonic() - started)
                row = LogRow(
                    timestamp=datetime.now(),
                    raw=raw,
                    weight_kg=weight,
                    smoothed_weight_kg=smoothed,
                    state=result.state.value,
                    event=result.event,
                )
                logger.write(row)
                write_status(
                    config.status_path,
                    make_status(
                        raw=raw,
                        weight_kg=weight,
                        smoothed_weight_kg=smoothed,
                        state=result.state.value,
                        event=result.event,
                    ),
                )
                if result.event:
                    for warning in alarm.handle_event(
                        event=result.event,
                        state=result.state.value,
                        weight_kg=weight,
                        smoothed_weight_kg=smoothed,
                        timestamp=row.timestamp,
                    ):
                        print(f"WARNING: {warning}", file=sys.stderr, flush=True)
                    if not (config.alarm_enabled and result.event == ALARM_EVENT):
                        try:
                            notifier.send(
                                Notification(
                                    event=result.event,
                                    state=result.state.value,
                                    weight_kg=weight,
                                    smoothed_weight_kg=smoothed,
                                    timestamp=row.timestamp,
                                )
                            )
                        except RuntimeError as exc:
                            print(f"WARNING: {exc}", file=sys.stderr, flush=True)

                message = f"{row.timestamp.isoformat(timespec='seconds')} {smoothed:7.2f}kg {result.state.value}"
                if result.event:
                    message += f" event={result.event}"
                print(message, flush=True)

                sample_count += 1
                sleep_for = config.sample_interval_sec - (time.monotonic() - loop_started)
                if sleep_for > 0:
                    time.sleep(sleep_for)
    finally:
        write_status(config.status_path, make_status(running=False, message="stopped"))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="twodosumi")
    sub = parser.add_subparsers(dest="command", required=True)

    zero = sub.add_parser("calibrate-zero")
    zero.add_argument("--config", required=True)
    zero.add_argument("--samples", type=int, default=30)
    zero.set_defaults(func=calibrate_zero)

    scale = sub.add_parser("calibrate-scale")
    scale.add_argument("--config", required=True)
    scale.add_argument("--known-kg", type=float, required=True)
    scale.add_argument("--samples", type=int, default=30)
    scale.set_defaults(func=calibrate_scale)

    run_parser = sub.add_parser("run")
    run_parser.add_argument("--config", required=True)
    run_parser.add_argument("--secrets")
    run_parser.add_argument("--max-samples", type=int)
    run_parser.set_defaults(func=run)

    web_parser = sub.add_parser("web")
    web_parser.add_argument("--config", required=True)
    web_parser.add_argument("--secrets", required=True)
    web_parser.add_argument("--host", default="127.0.0.1")
    web_parser.add_argument("--port", type=int, default=8080)
    web_parser.set_defaults(func=web)
    return parser


def web(args: argparse.Namespace) -> int:
    from .web import run_web

    run_web(args.config, args.secrets, args.host, args.port)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))
