"""
Turning a cadence into concrete due datetimes.

Occurrences are materialized ahead of time rather than computed on read, so that
"what did I miss last March" stays answerable and escalation state has somewhere
to live.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from nora_home.tracker.models import Cadence, Occurrence, Trackable

logger = logging.getLogger(__name__)

HORIZON_DAYS = 14  # how far ahead we materialize
DEFAULT_DUE_TIME = time(18, 0)


def next_due_dates(trackable: Trackable, after: date, count: int = 8) -> list[date]:
    """The next `count` dates this trackable falls due, strictly after `after`."""
    cadence = trackable.cadence
    start = max(after + timedelta(days=1), trackable.starts_on)
    dates: list[date] = []
    cursor = start

    if cadence == Cadence.ONCE:
        target = trackable.starts_on
        return [target] if target > after else []

    if cadence == Cadence.CRON:
        return _cron_dates(trackable, after, count)

    guard = 0
    while len(dates) < count and guard < 4000:
        guard += 1
        if trackable.ends_on and cursor > trackable.ends_on:
            break
        if _matches(cadence, trackable, cursor):
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


def _matches(cadence: str, trackable: Trackable, day: date) -> bool:
    if cadence == Cadence.DAILY:
        return True
    if cadence == Cadence.WEEKDAYS:
        return day.weekday() < 5
    if cadence == Cadence.WEEKLY:
        return day.weekday() == trackable.starts_on.weekday()
    if cadence == Cadence.MONTHLY:
        return day.day == _clamp_day(trackable.starts_on.day, day)
    if cadence == Cadence.QUARTERLY:
        months = (day.year - trackable.starts_on.year) * 12 + \
                 (day.month - trackable.starts_on.month)
        return months % 3 == 0 and day.day == _clamp_day(trackable.starts_on.day, day)
    if cadence == Cadence.YEARLY:
        return (day.month, day.day) == (trackable.starts_on.month, trackable.starts_on.day)
    if cadence == Cadence.INTERVAL:
        step = trackable.interval_days or 1
        return (day - trackable.starts_on).days % step == 0
    return False


def _clamp_day(wanted: int, in_month: date) -> int:
    """The 31st of February is the 28th (or 29th). Keeps monthly chores from
    silently skipping short months."""
    last = calendar.monthrange(in_month.year, in_month.month)[1]
    return min(wanted, last)


def _cron_dates(trackable: Trackable, after: date, count: int) -> list[date]:
    try:
        from croniter import croniter
    except ImportError:
        logger.error("croniter is not installed; cron trackable %s cannot be scheduled",
                     trackable.pk)
        return []
    try:
        base = datetime.combine(after, time.min)
        iterator = croniter(trackable.cron_expression, base)
        seen: list[date] = []
        while len(seen) < count:
            candidate = iterator.get_next(datetime).date()
            if trackable.ends_on and candidate > trackable.ends_on:
                break
            if candidate not in seen:
                seen.append(candidate)
        return seen
    except Exception:
        logger.exception("Bad cron expression on trackable %s: %r",
                         trackable.pk, trackable.cron_expression)
        return []


def due_datetime(trackable: Trackable, day: date):
    """Combine a due date with the trackable's due time, in the house timezone."""
    at = trackable.due_time or DEFAULT_DUE_TIME
    naive = datetime.combine(day, at)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def materialize(trackable: Trackable, horizon_days: int = HORIZON_DAYS) -> int:
    """Create the occurrences due within the horizon. Idempotent."""
    if not trackable.is_active or trackable.deleted_at:
        return 0

    today = timezone.localdate()
    horizon = today + timedelta(days=horizon_days)
    last_known = (trackable.occurrences.order_by("-due_at").values_list("due_at", flat=True)
                  .first())
    after = timezone.localtime(last_known).date() if last_known else \
        trackable.starts_on - timedelta(days=1)

    created = 0
    for day in next_due_dates(trackable, after, count=64):
        if day > horizon:
            break
        when = due_datetime(trackable, day)
        _, was_created = Occurrence.objects.get_or_create(
            trackable=trackable, due_at=when,
            defaults={"window_ends_at": when + timedelta(days=_window_days(trackable))},
        )
        created += int(was_created)

    upcoming = (trackable.occurrences.filter(status=Occurrence.Status.PENDING)
                .order_by("due_at").values_list("due_at", flat=True).first())
    if trackable.next_due_at != upcoming:
        trackable.next_due_at = upcoming
        trackable.save(update_fields=["next_due_at", "updated_at"])

    return created


def _window_days(trackable: Trackable) -> int:
    """How long an occurrence stays open before it counts as missed."""
    return {
        Cadence.DAILY: 1,
        Cadence.WEEKDAYS: 1,
        Cadence.WEEKLY: 3,
        Cadence.MONTHLY: 7,
        Cadence.QUARTERLY: 14,
        Cadence.YEARLY: 30,
    }.get(trackable.cadence, 7 if trackable.cadence != Cadence.ONCE else 30)
