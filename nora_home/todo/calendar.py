"""
Month-view calendar math (docs/Main_App/subsystems/todo.md §6, "Calendar").

Pure date arithmetic, deliberately separate from `views.py` so the tricky part
— building a complete grid of weeks, and expanding a yearly-recurring event
onto every year it's viewed — can be reasoned about and tested without a
request or a database in the way.

**Month view only, hand-written as a CSS grid.** Calendar libraries are large
and opinionated about how an event renders, and only one view is wanted here —
see the module docstring on why this project keeps choosing "one obviously
correct loop" over a vendored dependency for small, well-bounded date math
(`nora_home.todo.recurrence.fixed_dates` is the same call, for the same
reason).
"""

from __future__ import annotations

import calendar as _calendar
from datetime import date, timedelta

from django.utils import timezone

from nora_home.todo.models import EventRecurrence


def month_weeks(year: int, month: int) -> list[list[date]]:
    """Every date shown on the grid for `year`/`month`, grouped into
    Monday-starting weeks — including the leading and trailing days borrowed
    from the neighbouring months to fill out the first and last rows.
    """
    first_of_month = date(year, month, 1)
    last_day = _calendar.monthrange(year, month)[1]
    last_of_month = date(year, month, last_day)

    start = first_of_month - timedelta(days=first_of_month.weekday())
    end = last_of_month + timedelta(days=6 - last_of_month.weekday())

    days = []
    cursor = start
    while cursor <= end:
        days.append(cursor)
        cursor += timedelta(days=1)
    return [days[i:i + 7] for i in range(0, len(days), 7)]


def shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    """`(year, month)` shifted by `delta` months, rolling the year over
    correctly in either direction — December + 1 is next January, not month 13."""
    total = (year * 12 + (month - 1)) + delta
    return total // 12, total % 12 + 1


def _clamp_day(wanted: int, in_month: date) -> int:
    """The same reasoning as recurrence.py's own clamp: a birthday on the 29th
    still has to land somewhere in a 28-day February."""
    last = _calendar.monthrange(in_month.year, in_month.month)[1]
    return min(wanted, last)


def event_occurs_on(event, day: date) -> bool:
    """Does this event show on `day`? One-time events match their own date
    exactly; yearly ones match the month/day on *any* year, which is the
    entire point of a recurring birthday — it has to reappear every time the
    calendar scrolls past it, not just the year it was entered.
    """
    anchor = timezone.localtime(event.starts_at).date()
    if event.recurrence == EventRecurrence.YEARLY:
        return day.month == anchor.month and day.day == _clamp_day(anchor.day, day)
    return day == anchor


def events_by_day(events, days: list[date]) -> dict[date, list]:
    """Bucket `events` onto the `days` they fall on. A brute-force day-by-day
    check rather than per-recurrence-type arithmetic — the grid is at most six
    weeks and a house has a handful of events, so the obviously-correct loop
    costs nothing and needs no separate proof for the yearly case.
    """
    events = list(events)
    buckets: dict[date, list] = {day: [] for day in days}
    for day in days:
        for event in events:
            if event_occurs_on(event, day):
                buckets[day].append(event)
    return buckets
