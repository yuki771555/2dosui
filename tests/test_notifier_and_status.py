from datetime import datetime
import tempfile
from pathlib import Path
import unittest

from twodosumi.config import AppConfig, Secrets
from twodosumi.notifier import Notification, WebhookNotifier
from twodosumi.status import make_status, read_status, write_status


class NotifierAndStatusTests(unittest.TestCase):
    def test_discord_payload(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/a.csv",
            webhook_enabled=True,
            webhook_payload_format="discord",
        )
        notifier = WebhookNotifier(config, Secrets(webhook_url="http://example.test"))
        payload = notifier._payload(
            Notification(
                event="second_sleep_detected",
                state="SECOND_SLEEP",
                weight_kg=61,
                smoothed_weight_kg=60,
                timestamp=datetime(2026, 1, 1, 7, 0),
            )
        )
        self.assertIn("content", payload)
        self.assertIn("second_sleep_detected", payload["content"])

    def test_should_send_requires_enabled_url_and_selected_event(self):
        config = AppConfig(reader="mock", log_path="logs/a.csv")
        notifier = WebhookNotifier(config, Secrets(webhook_url="http://example.test"))
        self.assertFalse(notifier.should_send("second_sleep_detected"))

        config.webhook_enabled = True
        self.assertTrue(notifier.should_send("second_sleep_detected"))
        self.assertFalse(notifier.should_send("left_bed"))

    def test_status_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "status.json"
            write_status(path, make_status(state="SLEEPING", running=True))
            loaded = read_status(path)
            self.assertTrue(loaded["running"])
            self.assertEqual(loaded["state"], "SLEEPING")


if __name__ == "__main__":
    unittest.main()
