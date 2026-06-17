from datetime import datetime
import unittest

from twodosumi.alarm import SecondSleepAlarm
from twodosumi.config import AppConfig, Secrets, validate_config


class AlarmTests(unittest.TestCase):
    def test_alarm_disabled_ignores_second_sleep_event(self):
        config = AppConfig(reader="mock", log_path="logs/a.csv", alarm_enabled=False)
        alarm = SecondSleepAlarm(config, Secrets())
        warnings = alarm.handle_event(
            event="second_sleep_detected",
            state="SECOND_SLEEP",
            weight_kg=60,
            smoothed_weight_kg=60,
            timestamp=datetime.now(),
        )
        self.assertEqual(warnings, [])

    def test_alarm_enabled_without_buzzer_or_url_is_noop(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/a.csv",
            alarm_enabled=True,
            buzzer_enabled=False,
        )
        alarm = SecondSleepAlarm(config, Secrets())
        warnings = alarm.handle_event(
            event="second_sleep_detected",
            state="SECOND_SLEEP",
            weight_kg=60,
            smoothed_weight_kg=60,
            timestamp=datetime.now(),
        )
        self.assertEqual(warnings, [])

    def test_alarm_config_validation(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/a.csv",
            buzzer_duration_sec=0,
            buzzer_pulse_sec=0,
        )
        errors = validate_config(config)
        self.assertIn("buzzer_duration_sec must be greater than 0", errors)
        self.assertIn("buzzer_pulse_sec must be greater than 0", errors)


if __name__ == "__main__":
    unittest.main()
