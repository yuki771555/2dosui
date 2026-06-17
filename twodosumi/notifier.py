from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
import json
from typing import Any
from urllib import error, request

from .config import AppConfig, Secrets


@dataclass
class Notification:
    event: str
    state: str
    weight_kg: float
    smoothed_weight_kg: float
    timestamp: datetime


class WebhookNotifier:
    def __init__(self, config: AppConfig, secrets: Secrets) -> None:
        self.config = config
        self.secrets = secrets

    def should_send(self, event: str) -> bool:
        return bool(
            self.config.webhook_enabled
            and self.secrets.webhook_url
            and event
            and event in self.config.webhook_events
        )

    def send(self, notification: Notification) -> None:
        if not self.should_send(notification.event):
            return

        payload = self._payload(notification)
        body = json.dumps(payload).encode("utf-8")
        req = request.Request(
            self.secrets.webhook_url,
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=self.config.webhook_timeout_sec) as res:
                if res.status >= 400:
                    raise RuntimeError(f"webhook returned HTTP {res.status}")
        except (error.URLError, TimeoutError) as exc:
            raise RuntimeError(f"webhook send failed: {exc}") from exc

    def _payload(self, notification: Notification) -> dict[str, Any]:
        timestamp = notification.timestamp.isoformat(timespec="seconds")
        if self.config.webhook_payload_format == "discord":
            return {
                "content": (
                    f"2dosumi: {notification.event} "
                    f"({notification.smoothed_weight_kg:.2f} kg, {notification.state})"
                ),
                "embeds": [
                    {
                        "title": "2dosumi event",
                        "fields": [
                            {"name": "event", "value": notification.event, "inline": True},
                            {"name": "state", "value": notification.state, "inline": True},
                            {
                                "name": "weight",
                                "value": f"{notification.smoothed_weight_kg:.2f} kg",
                                "inline": True,
                            },
                        ],
                        "timestamp": timestamp,
                    }
                ],
            }

        data = asdict(notification)
        data["timestamp"] = timestamp
        return data


def send_test_webhook(config: AppConfig, secrets: Secrets) -> None:
    test_event = config.webhook_events[0] if config.webhook_events else "second_sleep_detected"
    test_config = replace(config, webhook_enabled=True, webhook_events=[test_event])
    WebhookNotifier(test_config, secrets).send(
        Notification(
            event=test_event,
            state="TEST",
            weight_kg=0.0,
            smoothed_weight_kg=0.0,
            timestamp=datetime.now(),
        )
    )
