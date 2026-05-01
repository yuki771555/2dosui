import unittest

from dosumi.state import BedState, BedStateMachine


class BedStateMachineTests(unittest.TestCase):
    def test_returned_within_monitor_window(self):
        machine = BedStateMachine(monitor_sec=1800, confirm_sec=180)
        self.assertIsNone(machine.update(1.0, 0))

        left = machine.update(0.1, 10)
        self.assertIsNotNone(left)
        self.assertEqual(left.current, BedState.AWAKE_WINDOW)

        returned = machine.update(0.8, 100)
        self.assertIsNotNone(returned)
        self.assertEqual(returned.current, BedState.RETURNED)

    def test_second_sleep_after_confirm_duration(self):
        machine = BedStateMachine(monitor_sec=1800, confirm_sec=180)
        machine.update(0.1, 10)
        machine.update(0.8, 100)

        self.assertIsNone(machine.update(0.8, 279))
        second_sleep = machine.update(0.8, 281)
        self.assertIsNotNone(second_sleep)
        self.assertEqual(second_sleep.current, BedState.SECOND_SLEEP)

    def test_done_after_monitor_window_expires(self):
        machine = BedStateMachine(monitor_sec=1800, confirm_sec=180)
        machine.update(0.1, 10)

        self.assertIsNone(machine.update(0.1, 1810))
        done = machine.update(0.1, 1811)
        self.assertIsNotNone(done)
        self.assertEqual(done.current, BedState.DONE)


if __name__ == "__main__":
    unittest.main()
