"""Injectable clock. The app uses real UTC time; tests install a fixed simulation clock
(2026-10-19 for the demo fixtures) and can move it forward."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from zoneinfo import ZoneInfo


class Clock:
    def now(self) -> datetime:
        return datetime.now(UTC)

    def today(self, time_zone: str) -> date:
        return self.now().astimezone(ZoneInfo(time_zone)).date()


class SimulationClock(Clock):
    def __init__(self, start: datetime) -> None:
        self._now = start.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)

    def set(self, moment: datetime) -> None:
        self._now = moment.astimezone(UTC)
