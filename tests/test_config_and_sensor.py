import tempfile
from pathlib import Path
import unittest

from twodosumi.config import AppConfig, load_config, save_config
from twodosumi.sensors import MockReader, median_raw, moving_average


class ConfigAndSensorTests(unittest.TestCase):
    def test_config_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.json"
            save_config(path, AppConfig(reader="mock", log_path="logs/a.csv"))
            loaded = load_config(path)
            self.assertEqual(loaded.reader, "mock")
            self.assertEqual(loaded.log_path, "logs/a.csv")

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


if __name__ == "__main__":
    unittest.main()

