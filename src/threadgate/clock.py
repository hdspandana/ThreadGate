"""Time source, injected.

Freshness is a security input: whether the vendor record on file is recent
enough to be trusted changes the decision. That makes the current date part of
the decision, so it must not be read ad hoc from `datetime.now()` at the point
of use. Tests and the evaluation pass a fixed instant; the running app passes
the system clock.

There is exactly one reason this module exists rather than a call to
`datetime.now()` inside `reference.py`: a clock that cannot be pinned makes
freshness-dependent behaviour untestable, and an untestable security input is
an unverified one.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone


@dataclass(frozen=True)
class FixedClock:
    """A clock pinned to one instant. Deterministic; used by tests and eval."""

    instant: datetime

    def now(self) -> datetime:
        return self.instant


class SystemClock:
    """The wall clock. Used by the running app, where real time is the point."""

    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def fixed(instant: str | date | datetime) -> FixedClock:
    """Build a FixedClock from an ISO date, a date, or a datetime.

    `fixed("2026-10-06")` is the form the tests use. Naive input is treated as
    UTC so that a date never silently lands in a different day than intended.
    """
    if isinstance(instant, datetime):
        dt = instant if instant.tzinfo else instant.replace(tzinfo=timezone.utc)
    elif isinstance(instant, date):
        dt = datetime(instant.year, instant.month, instant.day, tzinfo=timezone.utc)
    else:
        dt = datetime.fromisoformat(str(instant))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return FixedClock(dt)


def as_of(clock) -> date:
    """The calendar date a clock reports, in UTC."""
    return clock.now().astimezone(timezone.utc).date()
