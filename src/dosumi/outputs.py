from __future__ import annotations

import csv
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from .sources import Reading
from .state import BedState, Transition


class CsvLogger:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_header()

    def _ensure_header(self) -> None:
        if self.path.exists() and self.path.stat().st_size > 0:
            return
        with self.path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "raw", "weight_kg", "ratio", "state"])

    def write(self, reading: Reading, state: BedState) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(
                [
                    time.strftime("%Y-%m-%dT%H:%M:%S%z", time.localtime(reading.timestamp)),
                    f"{reading.raw:.3f}",
                    f"{reading.weight_kg:.3f}",
                    f"{reading.ratio:.4f}",
                    state.value,
                ]
            )


class DiscordNotifier:
    def __init__(self, webhook_url: str, mention: str = "", enabled: bool = True):
        self.webhook_url = webhook_url
        self.mention = mention.strip()
        self.enabled = enabled and bool(webhook_url)

    def send(self, content: str) -> bool:
        if not self.enabled:
            return False
        body = {"content": f"{self.mention} {content}".strip()}
        req = urllib.request.Request(
            self.webhook_url,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as res:
                return 200 <= res.status < 300
        except (urllib.error.URLError, TimeoutError) as exc:
            print(f"[discord] send failed: {exc}", file=sys.stderr)
            return False


class Buzzer:
    def __init__(self, pin: int, duration_sec: float, enabled: bool):
        self.pin = pin
        self.duration_sec = duration_sec
        self.enabled = enabled
        self._gpio = None
        if enabled:
            self._gpio = self._init_gpio()

    def _init_gpio(self):
        try:
            import RPi.GPIO as GPIO
        except ImportError as exc:
            raise RuntimeError("RPi.GPIO is not installed or this is not a Raspberry Pi.") from exc
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.pin, GPIO.OUT)
        return GPIO

    def alert(self) -> None:
        if not self.enabled or self._gpio is None:
            return
        self._gpio.output(self.pin, self._gpio.HIGH)
        time.sleep(self.duration_sec)
        self._gpio.output(self.pin, self._gpio.LOW)

    def close(self) -> None:
        if self._gpio is not None:
            self._gpio.cleanup(self.pin)


def print_transition(transition: Transition) -> None:
    print(
        f"[state] {transition.previous.value} -> {transition.current.value}: {transition.reason}",
        flush=True,
    )
