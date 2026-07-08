from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .config import AppConfig


class State(str, Enum):
    SLEEPING = "SLEEPING"
    AWAKE_WINDOW = "AWAKE_WINDOW"
    RETURNED = "RETURNED"
    SECOND_SLEEP = "SECOND_SLEEP"
    DONE = "DONE"


@dataclass
class DetectorResult:
    state: State
    event: str = ""


class SecondSleepDetector:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.state = State.SLEEPING
        self.wake_time: float | None = None
        self.return_start: float | None = None

    def update(self, weight_kg: float, now: float) -> DetectorResult:
        ratio = weight_kg / self.config.person_weight_kg
        event = ""

        if self.state == State.SLEEPING and ratio < self.config.exit_ratio:
            self.wake_time = now
            self.return_start = None
            self.state = State.AWAKE_WINDOW
            event = "left_bed"

        elif self.state == State.AWAKE_WINDOW:
            assert self.wake_time is not None
            if now - self.wake_time > self.config.monitor_sec:
                self.state = State.DONE
                event = "monitor_done"
            elif ratio > self.config.return_ratio:
                self.return_start = now
                self.state = State.RETURNED
                event = "returned"

        elif self.state == State.RETURNED:
            assert self.return_start is not None
            if ratio < self.config.return_ratio:
                self.return_start = None
                self.state = State.AWAKE_WINDOW
                event = "return_cancelled"
            elif now - self.return_start > self.config.confirm_sec:
                self.state = State.SECOND_SLEEP
                event = "second_sleep_detected"

        return DetectorResult(state=self.state, event=event)

