from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
import time

from .config import AppConfig, load_config, save_config
from .detector import SecondSleepDetector
from .logger import CsvLogger, LogRow
from .sensors import create_reader, median_raw, moving_average, warmup


def _raw_to_weight(raw: float, config: AppConfig) -> float:
    if config.scale_factor == 0:
        raise ValueError("scale_factor must not be 0")
    return (raw - config.zero_offset) / config.scale_factor


def calibrate_zero(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    reader = create_reader(config)
    warmup(reader, config.warmup_samples)
    zero = median_raw(reader, args.samples)
    config.zero_offset = zero
    save_config(args.config, config)
    print(f"ZERO_OFFSET saved: {zero:.3f}")
    return 0


def calibrate_scale(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    reader = create_reader(config)
    warmup(reader, config.warmup_samples)
    raw = median_raw(reader, args.samples)
    config.scale_factor = (raw - config.zero_offset) / args.known_kg
    save_config(args.config, config)
    print(f"SCALE_FACTOR saved: {config.scale_factor:.6f}")
    return 0


def run(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    reader = create_reader(config)
    detector = SecondSleepDetector(config)
    weights: deque[float] = deque(maxlen=max(1, config.moving_average_window))

    warmup(reader, config.warmup_samples)
    started = time.monotonic()
    sample_count = 0

    with CsvLogger(config.log_path) as logger:
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
            message = f"{row.timestamp.isoformat(timespec='seconds')} {smoothed:7.2f}kg {result.state.value}"
            if result.event:
                message += f" event={result.event}"
            print(message, flush=True)

            sample_count += 1
            sleep_for = config.sample_interval_sec - (time.monotonic() - loop_started)
            if sleep_for > 0:
                time.sleep(sleep_for)
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
    run_parser.add_argument("--max-samples", type=int)
    run_parser.set_defaults(func=run)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))

