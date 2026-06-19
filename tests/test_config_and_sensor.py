import tempfile
from pathlib import Path
import unittest

from twodosumi.config import AppConfig, ScheduledAlarmConfig, load_config, save_config, validate_config
from twodosumi.sensors import MockReader, check_sensor, median_raw, moving_average


class ConfigAndSensorTests(unittest.TestCase):
    def test_config_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(path, AppConfig(reader="mock", log_path="logs/a.csv"))
            loaded = load_config(path)
            self.assertEqual(loaded.reader, "mock")
            self.assertEqual(loaded.log_path, "logs/a.csv")

    def test_scheduled_alarm_config_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(
                path,
                AppConfig(
                    reader="mock",
                    log_path="logs/a.csv",
                    scheduled_alarms=[
                        ScheduledAlarmConfig(
                            id="morning",
                            time="07:30",
                            label="Wake up",
                            weekdays=[0, 1, 2, 3, 4],
                        )
                    ],
                ),
            )
            loaded = load_config(path)
            self.assertEqual(loaded.scheduled_alarms[0].id, "morning")
            self.assertEqual(loaded.scheduled_alarms[0].time, "07:30")
            self.assertEqual(loaded.scheduled_alarms[0].weekdays, [0, 1, 2, 3, 4])

    def test_scheduled_alarm_config_validation(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/a.csv",
            wake_mission_required_off_bed_sec=0,
            scheduled_alarms=[
                ScheduledAlarmConfig(id="morning", time="25:00", weekdays=[7]),
                ScheduledAlarmConfig(id="morning", time="07:00"),
            ],
        )
        errors = validate_config(config)
        self.assertIn("wake_mission_required_off_bed_sec must be greater than 0", errors)
        self.assertIn("duplicate scheduled alarm id: morning", errors)
        self.assertIn("scheduled alarm morning time must be HH:MM", errors)
        self.assertIn("scheduled alarm morning weekdays must be 0 through 6", errors)

    def test_mock_reader_sequence(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/a.csv",
            scale_factor=10,
            mock_sequence=[
                {"samples": 2, "weight_kg": 1},
                {"samples": 1, "weight_kg": 2},
            ],
        )
        reader = MockReader(config)
        self.assertEqual(reader.read_raw(), 10)
        self.assertEqual(reader.read_raw(), 10)
        self.assertEqual(reader.read_raw(), 20)
        self.assertEqual(reader.read_raw(), 20)

    def test_median_and_average(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/a.csv",
            mock_sequence=[
                {"samples": 1, "weight_kg": 1},
                {"samples": 1, "weight_kg": 100},
                {"samples": 1, "weight_kg": 2},
            ],
        )
        reader = MockReader(config)
        self.assertEqual(median_raw(reader, 3, interval_sec=0), 2)
        self.assertEqual(moving_average([1, 2, 3]), 2)

    def test_check_sensor_returns_raw_summary(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/a.csv",
            scale_factor=10,
            warmup_samples=0,
            mock_sequence=[
                {"samples": 1, "weight_kg": 1},
                {"samples": 1, "weight_kg": 2},
                {"samples": 1, "weight_kg": 3},
            ],
        )
        result = check_sensor(config, samples=3, interval_sec=0)
        self.assertTrue(result.ok)
        self.assertEqual(result.samples_read, 3)
        self.assertEqual(result.raw_min, 10)
        self.assertEqual(result.raw_max, 30)
        self.assertEqual(result.weight_median_kg, 2)


if __name__ == "__main__":
    unittest.main()

