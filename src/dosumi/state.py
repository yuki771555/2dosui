from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BedState(str, Enum):
    SLEEPING = "SLEEPING"
    AWAKE_WINDOW = "AWAKE_WINDOW"
    RETURNED = "RETURNED"
    SECOND_SLEEP = "SECOND_SLEEP"
    DONE = "DONE"


@dataclass(frozen=True)
class Transition:
    previous: BedState
    current: BedState
    reason: str


@dataclass
class BedStateMachine:
    exit_ratio: float = 0.30
    return_ratio: float = 0.40
    monitor_sec: int = 1800
    confirm_sec: int = 180
    state: BedState = BedState.SLEEPING
    wake_time: float | None = None
    return_start: float | None = None
    alerted: bool = False

    def update(self, weight_ratio: float, now: float) -> Transition | None:
        previous = self.state

        if self.state == BedState.SLEEPING and weight_ratio < self.exit_ratio:
            self.wake_time = now
            self.state = BedState.AWAKE_WINDOW
            return Transition(previous, self.state, "load dropped below exit threshold")

        if self.state == BedState.AWAKE_WINDOW:
            if self.wake_time is not None and now - self.wake_time > self.monitor_sec:
                self.state = BedState.DONE
                return Transition(previous, self.state, "monitor window expired")
            if weight_ratio > self.return_ratio:
                self.return_start = now
                self.state = BedState.RETURNED
                return Transition(previous, self.state, "load rose above return threshold")

        if self.state == BedState.RETURNED:
            if weight_ratio < self.return_ratio:
                self.return_start = None
                self.state = BedState.AWAKE_WINDOW
                return Transition(previous, self.state, "return load dropped before confirmation")
            if self.return_start is not None and now - self.return_start > self.confirm_sec:
                self.state = BedState.SECOND_SLEEP
                self.alerted = True
                return Transition(previous, self.state, "return load persisted beyond confirmation")

        return None
