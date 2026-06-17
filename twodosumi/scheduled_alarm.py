from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from .alarm import REALARM_EVENT, SCHEDULED_ALARM_EVENT
from .config import AppConfig, ScheduledAlarmConfig


DISMISSED_EVENT = "alarm_dismissed"


@dataclass
class ScheduledAlarmAction:
    event: str
    message: str
    alarm_ids: list[str]


@dataclass
class PendingRecheck:
    alarm: ScheduledAlarmConfig
    alarm_date: date
    due_at: datetime


class ScheduledAlarmManager:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self._completed: set[tuple[date, str]] = set()
        self._pending: dict[str, PendingRecheck] = {}

    def update(self, *, now: datetime, smoothed_weight_kg: float) -> list[ScheduledAlarmAction]:
        if not self.config.scheduled_alarm_enabled:
            return []

        self._forget_old_days(now.date())
        actions: list[ScheduledAlarmAction] = []
        in_bed = self._is_in_bed(smoothed_weight_kg)

        for alarm_id, pending in list(self._pending.items()):
            if not in_bed:
                actions.append(
                    ScheduledAlarmAction(
                        event=DISMISSED_EVENT,
                        message=f"Alarm dismissed: {self._alarm_name(pending.alarm)}",
                        alarm_ids=[alarm_id],
                    )
                )
                self._complete(pending.alarm_date, alarm_id)
                del self._pending[alarm_id]
            elif now >= pending.due_at:
                actions.append(
                    ScheduledAlarmAction(
                        event=REALARM_EVENT,
                        message=f"Still in bed: {self._alarm_name(pending.alarm)}",
                        alarm_ids=[alarm_id],
                    )
                )
                self._complete(pending.alarm_date, alarm_id)
                del self._pending[alarm_id]

        due = [
            alarm
            for alarm in self.config.scheduled_alarms
            if self._is_due(alarm, now) and (now.date(), alarm.id) not in self._completed
        ]
        if not due:
            return actions

        if not in_bed:
            actions.append(
                ScheduledAlarmAction(
                    event=DISMISSED_EVENT,
                    message=f"Already out of bed: {self._alarm_names(due)}",
                    alarm_ids=[alarm.id for alarm in due],
                )
            )
            for alarm in due:
                self._complete(now.date(), alarm.id)
            return actions

        recheck_at = now + timedelta(minutes=self.config.bed_recheck_minutes)
        for alarm in due:
            self._pending[alarm.id] = PendingRecheck(alarm=alarm, alarm_date=now.date(), due_at=recheck_at)
            self._completed.add((now.date(), alarm.id))
        actions.append(
            ScheduledAlarmAction(
                event=SCHEDULED_ALARM_EVENT,
                message=f"Alarm: {self._alarm_names(due)}",
                alarm_ids=[alarm.id for alarm in due],
            )
        )
        return actions

    def snapshot(self, *, now: datetime) -> dict[str, object]:
        next_alarm = self._next_alarm(now)
        return {
            "next_scheduled_alarm": self._serialize_alarm(next_alarm) if next_alarm else None,
            "pending_rechecks": [
                {
                    "id": pending.alarm.id,
                    "time": pending.alarm.time,
                    "label": pending.alarm.label,
                    "due_at": pending.due_at.isoformat(timespec="seconds"),
                }
                for pending in self._pending.values()
            ],
        }

    def _is_in_bed(self, smoothed_weight_kg: float) -> bool:
        ratio = smoothed_weight_kg / self.config.person_weight_kg
        return ratio >= self.config.exit_ratio

    def _is_due(self, alarm: ScheduledAlarmConfig, now: datetime) -> bool:
        if not alarm.enabled or now.weekday() not in alarm.weekdays:
            return False
        hour, minute = self._parse_time(alarm.time)
        return now.hour == hour and now.minute == minute

    def _complete(self, alarm_date: date, alarm_id: str) -> None:
        self._completed.add((alarm_date, alarm_id))

    def _forget_old_days(self, today: date) -> None:
        self._completed = {key for key in self._completed if key[0] == today}
        for alarm_id, pending in list(self._pending.items()):
            if pending.alarm_date != today:
                del self._pending[alarm_id]

    def _next_alarm(self, now: datetime) -> ScheduledAlarmConfig | None:
        enabled = [alarm for alarm in self.config.scheduled_alarms if alarm.enabled and alarm.weekdays]
        if not enabled:
            return None
        candidates: list[tuple[datetime, ScheduledAlarmConfig]] = []
        for days_ahead in range(8):
            day = now.date() + timedelta(days=days_ahead)
            for alarm in enabled:
                if day.weekday() not in alarm.weekdays:
                    continue
                hour, minute = self._parse_time(alarm.time)
                candidate = datetime.combine(day, now.time()).replace(
                    hour=hour, minute=minute, second=0, microsecond=0
                )
                if candidate > now:
                    candidates.append((candidate, alarm))
        if not candidates:
            return None
        return sorted(candidates, key=lambda item: item[0])[0][1]

    def _serialize_alarm(self, alarm: ScheduledAlarmConfig) -> dict[str, object]:
        return {
            "id": alarm.id,
            "time": alarm.time,
            "enabled": alarm.enabled,
            "label": alarm.label,
            "weekdays": alarm.weekdays,
        }

    def _alarm_names(self, alarms: list[ScheduledAlarmConfig]) -> str:
        return ", ".join(self._alarm_name(alarm) for alarm in alarms)

    def _alarm_name(self, alarm: ScheduledAlarmConfig) -> str:
        label = f" {alarm.label}" if alarm.label else ""
        return f"{alarm.time}{label}"

    def _parse_time(self, value: str) -> tuple[int, int]:
        hour, minute = value.split(":", 1)
        return int(hour), int(minute)
