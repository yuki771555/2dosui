from datetime import datetime
import unittest

from twodosumi.alarm import REALARM_EVENT, SCHEDULED_ALARM_EVENT
from twodosumi.config import AppConfig, ScheduledAlarmConfig
from twodosumi.scheduled_alarm import DISMISSED_EVENT, ScheduledAlarmManager


class ScheduledAlarmTests(unittest.TestCase):
    def test_scheduled_alarm_fires_once_and_realarms_if_still_in_bed(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/test.csv",
            person_weight_kg=60,
            bed_recheck_minutes=5,
            scheduled_alarms=[
                ScheduledAlarmConfig(id="morning", time="07:00", weekdays=[0]),
            ],
        )
        manager = ScheduledAlarmManager(config)

        first = manager.update(now=datetime(2026, 6, 15, 7, 0, 5), smoothed_weight_kg=60)
        self.assertEqual([action.event for action in first], [SCHEDULED_ALARM_EVENT])

        repeated = manager.update(now=datetime(2026, 6, 15, 7, 0, 45), smoothed_weight_kg=60)
        self.assertEqual(repeated, [])

        recheck = manager.update(now=datetime(2026, 6, 15, 7, 5, 5), smoothed_weight_kg=60)
        self.assertEqual([action.event for action in recheck], [REALARM_EVENT])

    def test_scheduled_alarm_dismisses_when_already_out_of_bed(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/test.csv",
            person_weight_kg=60,
            scheduled_alarms=[
                ScheduledAlarmConfig(id="morning", time="07:00", weekdays=[0]),
            ],
        )
        manager = ScheduledAlarmManager(config)

        actions = manager.update(now=datetime(2026, 6, 15, 7, 0, 0), smoothed_weight_kg=0)
        self.assertEqual([action.event for action in actions], [DISMISSED_EVENT])

    def test_pending_recheck_dismisses_after_leaving_bed(self):
        config = AppConfig(
            reader="mock",
            log_path="logs/test.csv",
            person_weight_kg=60,
            scheduled_alarms=[
                ScheduledAlarmConfig(id="morning", time="07:00", weekdays=[0]),
            ],
        )
        manager = ScheduledAlarmManager(config)

        manager.update(now=datetime(2026, 6, 15, 7, 0, 0), smoothed_weight_kg=60)
        actions = manager.update(now=datetime(2026, 6, 15, 7, 2, 0), smoothed_weight_kg=0)
        self.assertEqual([action.event for action in actions], [DISMISSED_EVENT])


if __name__ == "__main__":
    unittest.main()
