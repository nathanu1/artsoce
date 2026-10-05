"""Simulation clock, independent of wall time (spec K-1).

The reference configuration uses 10 simulated seconds per step and starts on
Monday 13 February 2023 00:00:00, as in base_the_ville_n25/reverie/meta.json.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta


@dataclass
class SimClock:
    start: datetime
    seconds_per_step: int = 10
    step: int = 0

    @property
    def now(self) -> datetime:
        return self.start + timedelta(seconds=self.step * self.seconds_per_step)

    def time_at(self, step: int) -> datetime:
        return self.start + timedelta(seconds=step * self.seconds_per_step)

    def advance(self, steps: int = 1) -> datetime:
        self.step += steps
        return self.now

    def steps_until(self, t: datetime) -> int:
        delta = (t - self.start).total_seconds()
        return int(delta // self.seconds_per_step)

    @property
    def today(self) -> date:
        return self.now.date()

    def is_new_day(self, previous: datetime | None) -> bool:
        return previous is None or previous.date() != self.now.date()


def day_label(t: datetime) -> str:
    """'Monday February 13' — weekday computed from the date (spec K-1)."""

    return f"{t.strftime('%A')} {t.strftime('%B')} {t.day}"


def long_time(t: datetime) -> str:
    """'February 13, 2023, 4:56 pm' as in the paper's prompts (p. 11)."""

    hour = t.hour % 12 or 12
    ampm = "am" if t.hour < 12 else "pm"
    return f"{t.strftime('%B')} {t.day}, {t.year}, {hour}:{t.minute:02d} {ampm}"


def clock_time(t: datetime) -> str:
    hour = t.hour % 12 or 12
    ampm = "am" if t.hour < 12 else "pm"
    return f"{hour}:{t.minute:02d} {ampm}"


def hhmm(t: datetime) -> str:
    return f"{t.hour:02d}:{t.minute:02d}"


def parse_hhmm(text: str, day: date) -> datetime:
    """Parse '07:30', '7:30 am', '7 pm', '19:00' into a datetime on ``day``.

    '24:00' maps to midnight at the end of ``day``.
    """

    s = text.strip().lower().replace(".", "")
    ampm = None
    for suffix in ("am", "pm"):
        if s.endswith(suffix):
            ampm = suffix
            s = s[: -len(suffix)].strip()
    if ":" in s:
        h_str, m_str = s.split(":", 1)
    else:
        h_str, m_str = s, "0"
    hour, minute = int(h_str), int(m_str)
    if ampm == "pm" and hour != 12:
        hour += 12
    if ampm == "am" and hour == 12:
        hour = 0
    if hour == 24 and minute == 0:
        return datetime(day.year, day.month, day.day) + timedelta(days=1)
    if not (0 <= hour < 24 and 0 <= minute < 60):
        raise ValueError(f"invalid clock time: {text!r}")
    return datetime(day.year, day.month, day.day, hour, minute)


def minutes_since_midnight(t: datetime) -> int:
    return t.hour * 60 + t.minute
