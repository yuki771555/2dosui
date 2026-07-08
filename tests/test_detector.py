import unittest

from twodosumi.config import AppConfig
from twodosumi.detector import SecondSleepDetector, State


class DetectorTests(unittest.TestCase):
    def test_second_sleep_flow(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/test.csv",
            person_weight_kg=60,
            monitor_sec=30,
            confirm_sec=3,
        )
        detector = SecondSleepDetector(config)

        self.assertEqual(detector.update(60, 0).state, State.SLEEPING)
        left = detector.update(0, 1)
        self.assertEqual(left.state, State.AWAKE_WINDOW)
        self.assertEqual(left.event, "left_bed")
        returned = detector.update(60, 2)
        self.assertEqual(returned.state, State.RETURNED)
        self.assertEqual(returned.event, "returned")
        confirmed = detector.update(60, 6)
        self.assertEqual(confirmed.state, State.SECOND_SLEEP)
        self.assertEqual(confirmed.event, "second_sleep_detected")

    def test_monitor_done_without_return(self):
        config = AppConfig(reader="mock", log_path="logs/test.csv", monitor_sec=5)
        detector = SecondSleepDetector(config)

        detector.update(0, 1)
        done = detector.update(0, 7)
        self.assertEqual(done.state, State.DONE)
        self.assertEqual(done.event, "monitor_done")


if __name__ == "__main__":
    unittest.main()

