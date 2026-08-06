"""
Turning a task's recurrence rule into concrete due moments.

Two kinds, and the difference is the whole reason this module is careful
(docs/Main_App/subsystems/todo.md §5):

  **Fixed**    "every Monday", "the 1st of each month". Knowable years out,
               because it does not depend on what anyone did.
  **Rolling**  "3 days after I last completed it". The next date does not
               exist until the current one is finished — so it can only ever
               be computed one step at a time, and nothing here can look
               further ahead than that.

`Task.recurrence_spec` is a JSON dict whose shape depends on
`Task.recurrence_type`:

    FIXED:
      {"kind": "daily"}
      {"kind": "weekdays"}                      Mon-Fri
      {"kind": "weekly",   "weekdays": [0, 3]}  0 = Monday
      {"kind": "monthly",  "day": 15}           clamped in short months
      {"kind": "yearly",   "month": 3, "day": 14}
      {"kind": "interval", "days": 3}           counted from the anchor
    ROLLING:
      {"days": 3}

Any of them may carry `"ends_on": "2026-12-31"` to stop recurring.

A malformed spec yields no dates rather than raising. A recurrence nobody can
parse should leave the task sitting still and log loudly — not take down the
nightly materialisation job for every other task in the house.
"""

from __future__ import annotations

import calendar
import logging
from datetime import date, datetime, time, timedelta

from django.utils import timezone

from nora_home.todo.models import InstanceOutcome, RecurrenceType

logger = logging.getLogger(__name__)

# Matches TodoPreference.default_due_hour's own default. Used when a task has no
# due_time and its owner has expressed no preference — see §8.
FALLBACK_DUE_HOUR = 9

FIXED_KINDS = {"daily", "weekdays", "weekly", "monthly", "yearly", "interval"}


# ── the pieces a rule is evaluated against ───────────────────────────────────

def anchor_date(task) -> date:
    """The date a recurrence counts from.

    `due_on` when the task has one — that is the first occasion, and "every 3
    days" means every 3 days *from then*. Falling back to the creation date
    keeps a recurring task with no due date working rather than silently
    producing nothing.
    """
    if task.due_on:
        return task.due_on
    return timezone.localtime(task.created_at).date()


def due_time_for(task) -> time:
    """What time of day an occasion falls due.

    The task's own `due_time` wins. Otherwise the owner's preferred default
    hour (§8 — "date-only tasks fall due at a per-member default hour, 09:00"),
    and finally the module default if that member has never set one.
    """
    if task.due_time:
        return task.due_time

    hour = FALLBACK_DUE_HOUR
    # Import here rather than at module scope: this is called during
    # materialisation, and a missing preference row must not be an error.
    from nora_home.todo.models import TodoPreference

    preference = TodoPreference.objects.filter(member=task.owner).first()
    if preference is not None:
        hour = preference.default_due_hour
    return time(hour, 0)


def due_at_on(task, day: date) -> datetime:
    """Combine a due date with the task's due time, in the house timezone.

    Ambiguous local times (the hour that repeats when DST ends) resolve to the
    first of the two, which is Python's `fold=0` default. Nothing in this house
    schedules anything at 1am, so the alternative — carrying a policy for it —
    would be ceremony for a case that cannot arise.
    """
    naive = datetime.combine(day, due_time_for(task))
    return timezone.make_aware(naive, timezone.get_current_timezone())


def ends_on(task) -> date | None:
    raw = (task.recurrence_spec or {}).get("ends_on")
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except (TypeError, ValueError):
        logger.warning("Task %s has an unparseable recurrence ends_on: %r", task.pk, raw)
        return None


# ── fixed recurrence ─────────────────────────────────────────────────────────

def _clamp_day(wanted: int, in_month: date) -> int:
    """The 31st of February is the 28th (or 29th). Without this, a monthly task
    set for the 31st silently skips February, April, June, September and
    November — five months a year, invisibly."""
    last = calendar.monthrange(in_month.year, in_month.month)[1]
    return min(wanted, last)


def falls_due_on(task, day: date) -> bool:
    """Does this fixed-recurrence task fall due on `day`?"""
    spec = task.recurrence_spec or {}
    kind = spec.get("kind")
    anchor = anchor_date(task)

    if day < anchor:
        return False
    stop = ends_on(task)
    if stop and day > stop:
        return False

    if kind == "daily":
        return True
    if kind == "weekdays":
        return day.weekday() < 5
    if kind == "weekly":
        weekdays = spec.get("weekdays")
        if not weekdays:
            # No explicit days: repeat on the anchor's own weekday, which is
            # what "weekly" means to someone who set a due date and nothing else.
            return day.weekday() == anchor.weekday()
        return day.weekday() in weekdays
    if kind == "monthly":
        wanted = spec.get("day") or anchor.day
        return day.day == _clamp_day(wanted, day)
    if kind == "yearly":
        month = spec.get("month") or anchor.month
        wanted = spec.get("day") or anchor.day
        return day.month == month and day.day == _clamp_day(wanted, day)
    if kind == "interval":
        # `spec.get("days") or 1` would be wrong here: 0 is falsy, so an
        # interval of 0 would silently become "every day" instead of being
        # rejected as the nonsense it is.
        step = spec.get("days", 1)
        if not isinstance(step, int) or isinstance(step, bool) or step < 1:
            logger.warning("Task %s has interval days=%r; ignoring", task.pk, step)
            return False
        return (day - anchor).days % step == 0

    logger.warning("Task %s has unknown fixed recurrence kind %r", task.pk, kind)
    return False


def fixed_dates(task, *, after: date, until: date) -> list[date]:
    """Every date in (`after`, `until`] this task falls due.

    Deliberately a day-by-day scan rather than arithmetic per kind: the window
    is 90 days, so this is at most 90 iterations, and one loop that is
    obviously correct beats six clever ones that each need their own edge-case
    proof around month lengths and leap years.
    """
    if task.recurrence_type != RecurrenceType.FIXED:
        return []
    if (task.recurrence_spec or {}).get("kind") not in FIXED_KINDS:
        logger.warning("Task %s has an unusable fixed recurrence spec: %r",
                       task.pk, task.recurrence_spec)
        return []

    dates: list[date] = []
    cursor = max(after + timedelta(days=1), anchor_date(task))
    while cursor <= until:
        if falls_due_on(task, cursor):
            dates.append(cursor)
        cursor += timedelta(days=1)
    return dates


# ── rolling recurrence ───────────────────────────────────────────────────────

def rolling_interval_days(task) -> int | None:
    days = (task.recurrence_spec or {}).get("days")
    if not isinstance(days, int) or days < 1:
        logger.warning("Task %s is rolling but has no usable days: %r",
                       task.pk, task.recurrence_spec)
        return None
    return days


def next_rolling_due(task) -> datetime | None:
    """When a rolling task next falls due.

    Counted from the **date of its last completion**, not from the moment: "3
    days after I did it" means three days later at the usual time, not 72 hours
    to the minute. Before the first completion the anchor is the task's own due
    date, so a rolling task starts when it was set to start rather than three
    days afterwards.

    Returns None once the rule has run out (`ends_on` passed), which is what
    stops materialisation creating anything further.
    """
    days = rolling_interval_days(task)
    if days is None:
        return None

    last = (task.instances
            .filter(outcome=InstanceOutcome.DONE, completed_at__isnull=False)
            .order_by("-completed_at")
            .values_list("completed_at", flat=True)
            .first())

    if last is None:
        day = anchor_date(task)
    else:
        day = timezone.localtime(last).date() + timedelta(days=days)

    stop = ends_on(task)
    if stop and day > stop:
        return None
    return due_at_on(task, day)
