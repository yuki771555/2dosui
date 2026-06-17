from __future__ import annotations

from dataclasses import replace
from datetime import datetime
import time

from .config import AppConfig, Secrets
from .notifier import Notification, WebhookNotifier


ALARM_EVENT = "second_sleep_detected"


class Buzzer:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._pin = None

    def __enter__(self) -> "Buzzer":
        return self

    def _ensure_pin(self) -> None:
        if self._pin is not None:
            return
        try:
            import board
            import digitalio
        except ImportError as exc:
            raise RuntimeError(
                "Buzzer requires Raspberry Pi GPIO dependencies. "
                "Install with: python3 -m pip install -r requirements-pi.txt"
            ) from exc

        pin_name = self.config.buzzer_pin
        try:
            board_pin = getattr(board, pin_name)
        except AttributeError as exc:
            raise RuntimeError(f"Unsupported buzzer_pin: {pin_name}") from exc
        pin = digitalio.DigitalInOut(board_pin)
        pin.direction = digitalio.Direction.OUTPUT
        pin.value = False
        self._pin = pin

    def __exit__(self, *_args: object) -> None:
        if self._pin is not None:
            self._pin.value = False
            self._pin.deinit()
            self._pin = None

    def ring(self) -> None:
        if not self.config.alarm_enabled or not self.config.buzzer_enabled:
            return
        self._ensure_pin()

        deadline = time.monotonic() + self.config.buzzer_duration_sec
        pulse = self.config.buzzer_pulse_sec
        while time.monotonic() < deadline:
            self._pin.value = True
            time.sleep(min(pulse, max(0, deadline - time.monotonic())))
            self._pin.value = False
            if time.monotonic() < deadline:
                time.sleep(min(pulse, max(0, deadline - time.monotonic())))


class SecondSleepAlarm:
    def __init__(self, config: AppConfig, secrets: Secrets) -> None:
        self.config = config
        alarm_config = replace(
            config,
            webhook_enabled=True,
            webhook_events=[ALARM_EVENT],
            webhook_payload_format="discord",
        )
        self.notifier = WebhookNotifier(alarm_config, secrets)
        self.buzzer = Buzzer(config)

    def __enter__(self) -> "SecondSleepAlarm":
        self.buzzer.__enter__()
        return self

    def __exit__(self, *_args: object) -> None:
        self.buzzer.__exit__(*_args)

    def handle_event(
        self,
        *,
        event: str,
        state: str,
        weight_kg: float,
        smoothed_weight_kg: float,
        timestamp: datetime,
    ) -> list[str]:
        if not self.config.alarm_enabled or event != ALARM_EVENT:
            return []

        warnings: list[str] = []
        notification = Notification(
            event=event,
            state=state,
            weight_kg=weight_kg,
            smoothed_weight_kg=smoothed_weight_kg,
            timestamp=timestamp,
        )
        try:
            self.notifier.send(notification)
        except RuntimeError as exc:
            warnings.append(str(exc))

        try:
            self.buzzer.ring()
        except RuntimeError as exc:
            warnings.append(str(exc))
        return warnings
