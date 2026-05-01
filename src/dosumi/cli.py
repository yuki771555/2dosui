from __future__ import annotations

import argparse
import shutil
import statistics
import sys
import time
from pathlib import Path

from .config import ensure_default_config, load_config, load_env, save_calibration
from .outputs import Buzzer, CsvLogger, DiscordNotifier, print_transition
from .sources import Hx711Source, SimulatedSource
from .state import BedState, BedStateMachine


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="2dosumi")
    parser.add_argument("--config", default="config.toml", help="Path to config.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Run the monitor")
    run.add_argument("--source", choices=["sim", "hx711"], default="sim")
    run.add_argument("--speed", type=float, default=1.0, help="Simulation speed multiplier")
    run.add_argument("--max-samples", type=int, default=0, help="Stop after N samples; 0 means forever")
    run.add_argument("--no-discord", action="store_true", help="Disable Discord for this run")
    run.add_argument("--no-buzzer", action="store_true", help="Disable buzzer for this run")

    zero = sub.add_parser("calibrate-zero", help="Measure and save HX711 zero offset")
    zero.add_argument("--source", choices=["sim", "hx711"], default="hx711")
    zero.add_argument("--readings", type=int, default=30)

    scale = sub.add_parser("calibrate-scale", help="Measure and save HX711 scale factor")
    scale.add_argument("--source", choices=["sim", "hx711"], default="hx711")
    scale.add_argument("--known-kg", type=float, required=True)
    scale.add_argument("--readings", type=int, default=30)

    install = sub.add_parser("install-service", help="Print systemd install commands")
    install.add_argument("--service-path", default="systemd/2dosumi.service")
    return parser


def make_source(source_name: str, cfg, speed: float = 1.0):
    if source_name == "sim":
        return SimulatedSource(cfg.runtime.body_weight_kg, cfg.runtime.sample_interval_sec, speed)
    return Hx711Source(cfg.hx711, cfg.runtime.body_weight_kg, cfg.runtime.sample_interval_sec)


def cmd_run(args: argparse.Namespace) -> int:
    ensure_default_config(args.config)
    cfg = load_config(args.config)
    env = load_env()
    source = make_source(args.source, cfg, args.speed)
    machine = BedStateMachine(
        exit_ratio=cfg.thresholds.exit_ratio,
        return_ratio=cfg.thresholds.return_ratio,
        monitor_sec=cfg.thresholds.monitor_sec,
        confirm_sec=cfg.thresholds.confirm_sec,
    )
    logger = CsvLogger(cfg.runtime.log_path)
    notifier = DiscordNotifier(
        env.get("DISCORD_WEBHOOK_URL", ""),
        mention=cfg.discord.mention,
        enabled=cfg.discord.enabled and not args.no_discord,
    )
    buzzer = Buzzer(
        pin=cfg.buzzer.pin,
        duration_sec=cfg.buzzer.duration_sec,
        enabled=cfg.buzzer.enabled and not args.no_buzzer,
    )

    print(f"[run] source={args.source} log={cfg.runtime.log_path}", flush=True)
    sent_alert = False
    try:
        for index, reading in enumerate(source.readings(), start=1):
            transition = machine.update(reading.ratio, reading.timestamp)
            logger.write(reading, machine.state)
            print(
                f"{index:06d} weight={reading.weight_kg:7.2f}kg ratio={reading.ratio:5.2f} state={machine.state.value}",
                flush=True,
            )
            if transition is not None:
                print_transition(transition)
                if transition.current == BedState.SECOND_SLEEP and not sent_alert:
                    message = (
                        "2度寝を検知しました。"
                        f" weight={reading.weight_kg:.1f}kg ratio={reading.ratio:.2f}"
                    )
                    notifier.send(message)
                    buzzer.alert()
                    sent_alert = True
            if args.max_samples and index >= args.max_samples:
                break
    finally:
        buzzer.close()
    return 0


def _collect_raw(source, count: int) -> list[float]:
    values = []
    for reading, _ in zip(source.readings(), range(count)):
        values.append(reading.raw)
        print(f"raw={reading.raw:.3f}")
    return values


def cmd_calibrate_zero(args: argparse.Namespace) -> int:
    ensure_default_config(args.config)
    cfg = load_config(args.config)
    source = make_source(args.source, cfg)
    values = _collect_raw(source, args.readings)
    zero = statistics.median(values)
    save_calibration(args.config, zero_offset=zero)
    print(f"Saved zero_offset={zero:.3f} to {args.config}")
    return 0


def cmd_calibrate_scale(args: argparse.Namespace) -> int:
    if args.known_kg <= 0:
        print("--known-kg must be greater than 0", file=sys.stderr)
        return 2
    ensure_default_config(args.config)
    cfg = load_config(args.config)
    source = make_source(args.source, cfg)
    values = _collect_raw(source, args.readings)
    loaded_raw = statistics.median(values)
    scale_factor = (loaded_raw - cfg.hx711.zero_offset) / args.known_kg
    save_calibration(args.config, scale_factor=scale_factor)
    print(f"Saved scale_factor={scale_factor:.6f} to {args.config}")
    return 0


def cmd_install_service(args: argparse.Namespace) -> int:
    service = Path(args.service_path)
    if not service.exists():
        print(f"Service file not found: {service}", file=sys.stderr)
        return 2
    print("Run these commands on the Raspberry Pi:")
    print(f"sudo cp {service} /etc/systemd/system/2dosumi.service")
    print("sudo systemctl daemon-reload")
    print("sudo systemctl enable 2dosumi")
    print("sudo systemctl start 2dosumi")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "run":
        return cmd_run(args)
    if args.command == "calibrate-zero":
        return cmd_calibrate_zero(args)
    if args.command == "calibrate-scale":
        return cmd_calibrate_scale(args)
    if args.command == "install-service":
        return cmd_install_service(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
