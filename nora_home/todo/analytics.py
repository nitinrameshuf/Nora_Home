"""
Every statistic Todo knows how to compute (docs/Main_App/subsystems/todo.md
§10 for what each one answers, §13 for the rules they all obey).

**This module is the AI-readiness contract.** The Reporting page calls these
functions, the widgets call these functions, the MCP tools call these
functions, and any future AI layer calls the same ones rather than
re-deriving a number of its own. One documented function per metric; nothing
anywhere else in this app is allowed to compute a statistic.

Three rules hold throughout, and each of them is load-bearing:

**1. Everything is computed from history on read. No cached counters, ever.**
History is retroactively editable (§4) — someone can correct a day three
weeks back at any moment — so a stored "19 of 30" goes silently wrong and
nobody ever finds out. §13 states this as the hard constraint precisely
because caching is the tempting optimisation that breaks it.

**2. "No data" is not zero, and every function says which it means.** A rate
of `None` means nothing was due; a rate of `0.0` means things were due and
none got done. Rendering the first as a zero tells someone they failed at a
week when the house asked nothing of them — which is exactly the accusation
§10's Tone section exists to avoid. This mirrors
`nora_home.tracker.api.completion_stats()`, which already made this choice.

**3. These functions return data, never presentation.** No ECharts options,
no HTML, no colours, and — importantly — **no tone**. `nora_home.todo.tone`
decides how a number is worded and whether it may be red; the number itself
is the same for everyone. A statistic that changed depending on how someone
prefers to be spoken to would not be a statistic.

Shared tasks: effort always goes through `api.effort_share_minutes()`, which
splits across assignees rather than multiplying (§4a). Counting a 60-minute
shared task in full for each of three people would tell three people they
each have a full day of what is really one hour of house work.
"""

from __future__ import annotations

import logging
from collections import Counter, defaultdict
from datetime import timedelta
from statistics import median

from django.db.models import Count
from django.utils import timezone

from nora_home.todo import api
from nora_home.todo.models import (
    ChangeEvent,
    Instance,
    InstanceOutcome,
    Priority,
    Task,
    TaskState,
)

logger = logging.getLogger(__name__)

# Outcomes that represent a finished occasion, for "did the work happen".
# `awaiting_approval` is deliberately absent: §4a is explicit that it "does not
# count as a completion in Reporting until approved."
DONE_OUTCOMES = (InstanceOutcome.DONE,)

# Outcomes that closed without the work happening. `skipped` is *not* a
# failure — §5: a skip declared before the due moment is a deliberate
# decision, "excluded from miss patterns" — so it is counted separately
# everywhere and never folded into misses.
MISSED_OUTCOMES = (InstanceOutcome.MISSED,)


# ── scoping ──────────────────────────────────────────────────────────────────

def tasks_of(members):
    """Live, person-facing tasks for these people. Deleted tasks are gone;
    archived ones stay, because "not now" is a state a chart should be able to
    show, not an erasure."""
    return api.tasks_for(members, queryset=Task.objects.alive())


def instances_of(members, *, since=None, until=None):
    """Every occasion belonging to these people's tasks, optionally windowed
    on the moment it was *due* — which is the axis nearly every chart here is
    drawn against, since it is the moment the house asked for something."""
    qs = Instance.objects.filter(task__in=tasks_of(members)).select_related("task")
    if since is not None:
        qs = qs.filter(due_at__gte=since)
    if until is not None:
        qs = qs.filter(due_at__lt=until)
    return qs


def _window(days: int):
    """(start, end) covering the last `days` days up to now. For anything
    bucketed by calendar day, use `_day_window()` instead."""
    now = timezone.now()
    return now - timedelta(days=days), now


def _day_window(days: int):
    """`(first_day, all_days, start_moment)` for the last `days` calendar days,
    **ending today inclusive**.

    Date-aligned rather than `now - N×24h`, and this is not a nicety. The
    naive version starts partway through the oldest day and — the bug it
    replaced — ends partway through *today*, so a loop of `range(days)` from
    that start never reaches today at all. Every day-bucketed chart silently
    dropped the current day, which is exactly where the data anyone is
    looking at the page for actually is: `cumulative_flow()` reported "no
    data" against a database that had some.
    """
    from datetime import datetime, time as _time

    today = timezone.localdate()
    first = today - timedelta(days=days - 1)
    start = timezone.make_aware(datetime.combine(first, _time.min))
    all_days = [first + timedelta(days=offset) for offset in range(days)]
    return first, all_days, start


def _local_date(moment):
    return timezone.localtime(moment).date()


# ── 1. Realistic load ────────────────────────────────────────────────────────

def typical_throughput(members, *, days: int = 90) -> dict:
    """"You typically finish 4–6 things." The honest answer to how much this
    person actually gets through in a day.

    Reported as a **median and an interquartile-ish band**, never a mean:
    completion counts are lumpy (a burst of five on Saturday, nothing Tuesday)
    and an average lands on a number that describes no real day. Days with no
    completions are counted as zeros — they are real days that really had
    none, and dropping them would inflate the figure into exactly the
    unreachable target §10 is trying not to set.

    `{"median": None, ...}` when the window holds no completed work at all.
    """
    _, all_days, start = _day_window(days)
    completed = (instances_of(members)
                 .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=start)
                 .values_list("completed_at", flat=True))

    per_day = Counter(_local_date(when) for when in completed)
    if not per_day:
        return {"median": None, "low": None, "high": None, "days_observed": 0,
                "total": 0}

    # Every day in the window, including the empty ones.
    counts = sorted(per_day.get(day, 0) for day in all_days)
    middle = median(counts)
    lower = counts[len(counts) // 4]
    upper = counts[(len(counts) * 3) // 4]

    return {"median": middle, "low": lower, "high": upper,
            "days_observed": days, "total": sum(counts)}


def open_load(members) -> dict:
    """What is actually open right now, and roughly how long it would take.

    The minutes figure goes through `api.effort_share_minutes()`, so a task
    shared three ways contributes a third of itself — see §4a. Tasks nobody
    estimated contribute nothing to `minutes` and are counted in
    `unestimated`, because silently treating "no estimate" as zero would make
    a full day look empty.
    """
    pending = (instances_of(members)
               .filter(outcome=InstanceOutcome.PENDING,
                       task__state=TaskState.OPEN)
               .select_related("task"))

    minutes = 0.0
    unestimated = 0
    count = 0
    overdue = 0
    now = timezone.now()
    for instance in pending:
        count += 1
        if instance.due_at < now:
            overdue += 1
        share = api.effort_share_minutes(instance)
        if share is None:
            unestimated += 1
        else:
            minutes += share

    return {"count": count, "overdue": overdue,
            "minutes": round(minutes) if count else 0,
            "unestimated": unestimated}


# ── 2. Deferral patterns ─────────────────────────────────────────────────────

def deferral_by_label(members, *, days: int = 180) -> list[dict]:
    """Which labels keep sliding, and by how much.

    Reads the `due_on` rows of the `ChangeEvent` trail (`api.record_changes`)
    — actual, dated reschedules, not a counter. A task with no label at all is
    reported under `None` rather than dropped, since "the things I never got
    round to labelling" is frequently the answer.

    `[]` when nothing has been rescheduled, which is a real and good answer.
    """
    since, _ = _window(days)
    moves = (ChangeEvent.objects
             .filter(field="due_on", created_at__gte=since,
                     task__in=tasks_of(members))
             .select_related("task")
             .prefetch_related("task__labels"))

    by_label: dict[str | None, list[int]] = defaultdict(list)
    for move in moves:
        shift = _days_between(move.from_value, move.to_value)
        labels = [label.name for label in move.task.labels.all()] or [None]
        for label in labels:
            by_label[label].append(shift)

    rows = [{
        "label": label,
        "moves": len(shifts),
        # Median rather than total: one task pushed a year out should not make
        # a label look chronically deferred when nothing else in it ever moved.
        "median_days": median([s for s in shifts if s is not None]) if any(
            s is not None for s in shifts) else None,
    } for label, shifts in by_label.items()]

    return sorted(rows, key=lambda row: row["moves"], reverse=True)


def _days_between(from_value, to_value) -> int | None:
    """Whole days between two ISO dates stored on a ChangeEvent. `None` when
    either end is missing — a task that gained or lost its due date entirely
    moved, but not by a measurable number of days."""
    from datetime import date

    if not from_value or not to_value:
        return None
    try:
        return (date.fromisoformat(to_value) - date.fromisoformat(from_value)).days
    except (TypeError, ValueError):
        logger.warning("Unparseable due_on change: %r -> %r", from_value, to_value)
        return None


# ── 3. Time to first touch ───────────────────────────────────────────────────

def time_to_first_touch(members, *, days: int = 180) -> dict:
    """How long between writing something down and actually doing any of it.

    Measured task-by-task, from `Task.created_at` to its earliest completion.
    Only tasks that have been touched at all appear — an untouched task has no
    time-to-first-touch yet, and counting it as "infinity" would make the
    median meaningless.
    """
    since, _ = _window(days)
    tasks = tasks_of(members).filter(created_at__gte=since)

    gaps = []
    firsts = (Instance.objects
              .filter(task__in=tasks, outcome__in=DONE_OUTCOMES,
                      completed_at__isnull=False)
              .values("task_id", "task__created_at", "completed_at"))

    earliest: dict[int, tuple] = {}
    for row in firsts:
        key = row["task_id"]
        if key not in earliest or row["completed_at"] < earliest[key][1]:
            earliest[key] = (row["task__created_at"], row["completed_at"])

    for created, completed in earliest.values():
        gaps.append((completed - created).total_seconds() / 86400)

    if not gaps:
        return {"median_days": None, "tasks": 0, "same_day": 0}

    return {
        "median_days": round(median(gaps), 1),
        "tasks": len(gaps),
        "same_day": sum(1 for gap in gaps if gap < 1),
    }


# ── 4. Priority drift ────────────────────────────────────────────────────────

def priority_distribution(members) -> list[dict]:
    """What share of open work sits in each priority — "whether priority still
    means anything." When almost everything is Priority 1, nothing is.

    A current-state snapshot, not a history walk: the question is what the
    board looks like now.
    """
    counts = (tasks_of(members)
              .filter(state=TaskState.OPEN)
              .values("priority")
              .annotate(n=Count("id")))
    by_priority = {row["priority"]: row["n"] for row in counts}
    total = sum(by_priority.values())

    return [{
        "priority": value,
        "label": label,
        "count": by_priority.get(value, 0),
        "share": round(by_priority.get(value, 0) / total * 100, 1) if total else None,
    } for value, label in Priority.choices]


# ── 5. Aging ─────────────────────────────────────────────────────────────────

def aging_open_items(members, *, limit: int = 10) -> list[dict]:
    """The oldest things still open, so they can be dealt with or archived.

    §10 pairs this chart with "one-tap archive beside each", which is why the
    task's own uuid comes back with it — the page needs somewhere to point
    that button.
    """
    now = timezone.now()
    tasks = (tasks_of(members)
             .filter(state=TaskState.OPEN)
             .order_by("created_at")[:limit])

    return [{
        "uuid": str(task.uuid),
        "title": task.title,
        "priority": task.priority,
        "age_days": (now - task.created_at).days,
    } for task in tasks]


def aging_by_priority(members) -> list[dict]:
    """Open work bucketed by how long it has been sitting, per priority column
    — the work-in-progress ageing view. Buckets rather than a scatter, because
    "three things older than a month" is the actionable shape; the exact ages
    are what `aging_open_items()` is for."""
    now = timezone.now()
    buckets = ["< 1 week", "1–4 weeks", "1–3 months", "> 3 months"]
    grid = {value: dict.fromkeys(buckets, 0) for value, _ in Priority.choices}

    for task in tasks_of(members).filter(state=TaskState.OPEN):
        age = (now - task.created_at).days
        if age < 7:
            bucket = buckets[0]
        elif age < 28:
            bucket = buckets[1]
        elif age < 90:
            bucket = buckets[2]
        else:
            bucket = buckets[3]
        if task.priority in grid:
            grid[task.priority][bucket] += 1

    return [{"priority": value, "label": label, "buckets": grid[value]}
            for value, label in Priority.choices]


# ── 6. Evidence of agency ────────────────────────────────────────────────────

def recent_completions(members, *, limit: int = 20) -> list[dict]:
    """A plain list of what someone decided to do and then did.

    Deliberately the least clever function here. §10 calls it "evidence of
    agency" — the point is that it is *not* aggregated into a score. Reading
    back a list of real things you actually finished is the thing that helps;
    a number derived from them is not the same object.
    """
    done = (instances_of(members)
            .filter(outcome__in=DONE_OUTCOMES, completed_at__isnull=False)
            .select_related("task", "completed_by")
            .order_by("-completed_at")[:limit])

    return [{
        "uuid": str(instance.task.uuid),
        "title": instance.task.title,
        "completed_at": instance.completed_at,
        "by": instance.completed_by.name if instance.completed_by else None,
        "minutes": instance.effective_minutes,
    } for instance in done]


# ── 7. Recovery after gaps ───────────────────────────────────────────────────

def recoveries(members, *, days: int = 365, gap_days: int = 3) -> list[dict]:
    """Times someone stopped for a while and then came back.

    **Reported as a positive, and that is the whole point of the metric.** The
    conventional streak counter treats a nine-day gap as a failure and resets
    to zero, which for anyone prone to all-or-nothing thinking is an argument
    for never restarting. Counting the restarts instead makes returning the
    thing being measured.
    """
    since, _ = _window(days)
    completed = sorted({
        _local_date(when) for when in
        instances_of(members)
        .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=since)
        .values_list("completed_at", flat=True)
    })

    found = []
    for earlier, later in zip(completed, completed[1:]):
        gap = (later - earlier).days
        if gap > gap_days:
            found.append({"gap_days": gap, "returned_on": later, "last_before": earlier})
    return found


# ── 8. Cumulative flow ───────────────────────────────────────────────────────

def cumulative_flow(members, *, days: int = 60) -> dict:
    """Work arriving versus work completing — "is the pile growing?"

    Arrivals are counted on the day an occasion fell **due** (the day the
    house asked for it) and completions on the day it was actually finished,
    so a line pulling away from the other is real backlog rather than an
    artefact of when things were typed in.
    """
    _, all_days, start = _day_window(days)

    arrived = Counter()
    finished = Counter()
    for instance in instances_of(members, since=start):
        arrived[_local_date(instance.due_at)] += 1
    for when in (instances_of(members)
                 .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=start)
                 .values_list("completed_at", flat=True)):
        finished[_local_date(when)] += 1

    labels, arrived_cum, finished_cum = [], [], []
    running_in = running_out = 0
    for day in all_days:
        running_in += arrived.get(day, 0)
        running_out += finished.get(day, 0)
        labels.append(day.isoformat())
        arrived_cum.append(running_in)
        finished_cum.append(running_out)

    if not running_in and not running_out:
        return {"days": [], "arrived": [], "completed": []}
    return {"days": labels, "arrived": arrived_cum, "completed": finished_cum}


# ── 9. Cycle time ────────────────────────────────────────────────────────────

def cycle_times(members, *, days: int = 180) -> dict:
    """How long things take, two ways: created → done (how long it sat in the
    house at all) and due → done (how close to its moment it landed).

    The second can be negative — finished early — and is left signed on
    purpose. Clamping it to zero would erase the difference between "always
    just in time" and "usually a day ahead", which is most of what the number
    is for.
    """
    since, _ = _window(days)
    done = (instances_of(members)
            .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=since)
            .select_related("task"))

    created_to_done, due_to_done = [], []
    for instance in done:
        created_to_done.append(
            (instance.completed_at - instance.task.created_at).total_seconds() / 86400)
        due_to_done.append(
            (instance.completed_at - instance.due_at).total_seconds() / 86400)

    if not created_to_done:
        return {"created_to_done_days": None, "due_to_done_days": None, "count": 0}

    return {
        "created_to_done_days": round(median(created_to_done), 1),
        "due_to_done_days": round(median(due_to_done), 1),
        "count": len(created_to_done),
    }


# ── 10. Throughput histogram ─────────────────────────────────────────────────

def throughput_histogram(members, *, days: int = 90) -> dict:
    """The real distribution of "things finished in a day", not an average.

    §10 asks for the distribution specifically. A mean of 4.2 hides whether
    that is four every day or twenty on Sunday and nothing else; the shape
    answers a question the average cannot.
    """
    _, all_days, start = _day_window(days)
    completed = (instances_of(members)
                 .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=start)
                 .values_list("completed_at", flat=True))

    per_day = Counter(_local_date(when) for when in completed)
    if not per_day:
        return {"buckets": [], "counts": []}

    daily = [per_day.get(day, 0) for day in all_days]
    spread = Counter(daily)
    top = max(spread)
    return {"buckets": list(range(top + 1)),
            "counts": [spread.get(n, 0) for n in range(top + 1)]}


# ── 11. Calendar heatmap ─────────────────────────────────────────────────────

def completion_heatmap(members, *, days: int = 365) -> list[list]:
    """`[[iso_date, count], …]` — the GitHub-contributions shape, which
    ECharts draws natively from exactly this structure.

    Only days with something on them are returned; an empty day is an absent
    key, not a zero, so the caller can render "nothing yet" as a sentence
    rather than a year of empty cells.
    """
    since, _ = _window(days)
    completed = (instances_of(members)
                 .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=since)
                 .values_list("completed_at", flat=True))

    per_day = Counter(_local_date(when) for when in completed)
    return [[day.isoformat(), count] for day, count in sorted(per_day.items())]


# ── 12. Rhythm ───────────────────────────────────────────────────────────────

def completion_rhythm(members, *, days: int = 180) -> dict:
    """When work actually gets done — by hour of day and by weekday.

    Useful for the scheduling suggestions in §11 and, more immediately, for
    telling someone their "I'm not a morning person" belief is or isn't borne
    out by a year of their own behaviour.
    """
    since, _ = _window(days)
    completed = (instances_of(members)
                 .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=since)
                 .values_list("completed_at", flat=True))

    hours = [0] * 24
    weekdays = [0] * 7
    total = 0
    for when in completed:
        local = timezone.localtime(when)
        hours[local.hour] += 1
        weekdays[local.weekday()] += 1
        total += 1

    if not total:
        return {"hours": [], "weekdays": [], "total": 0}
    return {"hours": hours, "weekdays": weekdays, "total": total}


# ── 13. Label distribution ───────────────────────────────────────────────────

def label_distribution(members, *, days: int = 90) -> list[dict]:
    """Where attention actually goes, versus where someone thinks it goes.

    Counts **completed occasions** rather than tasks, so a daily habit and a
    one-off errand are weighted by how much they were really done, not by how
    many rows they occupy.
    """
    since, _ = _window(days)
    done = (instances_of(members)
            .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=since)
            .prefetch_related("task__labels"))

    counts: Counter = Counter()
    for instance in done:
        labels = [label.name for label in instance.task.labels.all()]
        for label in labels or [None]:
            counts[label] += 1

    return [{"label": label, "count": count}
            for label, count in counts.most_common()]


# ── 14. Estimate accuracy ────────────────────────────────────────────────────

def estimate_accuracy(members, *, days: int = 180) -> dict:
    """Planned versus actual, for the occasions where someone recorded both.

    `ratio` above 1 means things take longer than planned. Only instances with
    a *real* `actual_minutes` count — `effective_minutes` falls back to the
    plan when no actual was recorded (§3), and feeding that back in here would
    compare the estimate against itself and report perfect accuracy forever.
    That fallback is right for load calculations and wrong for this one.
    """
    since, _ = _window(days)
    done = (instances_of(members)
            .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=since,
                    actual_minutes__isnull=False,
                    task__planned_minutes__isnull=False)
            .select_related("task"))

    pairs = [(instance.task.planned_minutes, instance.actual_minutes)
             for instance in done if instance.task.planned_minutes]

    if not pairs:
        return {"ratio": None, "count": 0, "planned": [], "actual": []}

    ratios = [actual / planned for planned, actual in pairs]
    return {
        "ratio": round(median(ratios), 2),
        "count": len(pairs),
        "planned": [planned for planned, _ in pairs],
        "actual": [actual for _, actual in pairs],
    }


# ── 15. Streaks, in both shapes ──────────────────────────────────────────────

def streak(members, *, window: int = 30) -> dict:
    """Both shapes §10's Tone table offers, computed together and always
    returned together — the *preset* picks which one to show, not this
    function. Keeping both here is what lets someone switch tone and see the
    other number immediately, with no recomputation and no stored state.

    `ratio` is "19 of the last 30 days had something finished". `classic` is
    consecutive days up to today, resetting on any empty day.
    """
    since, _ = _window(window)
    active = {
        _local_date(when) for when in
        instances_of(members)
        .filter(outcome__in=DONE_OUTCOMES, completed_at__gte=since)
        .values_list("completed_at", flat=True)
    }

    today = timezone.localdate()
    consecutive = 0
    while (today - timedelta(days=consecutive)) in active:
        consecutive += 1

    return {"ratio_done": len(active), "ratio_of": window, "classic": consecutive}


# ── the whole picture, for one page load ─────────────────────────────────────

def overview(members) -> dict:
    """Everything the Reporting page needs, in one call.

    A convenience for the view and the MCP tools, not a new statistic — every
    value here comes from the functions above, so there is still exactly one
    place each number is computed.
    """
    return {
        "throughput": typical_throughput(members),
        "load": open_load(members),
        "streak": streak(members),
        "first_touch": time_to_first_touch(members),
        "cycle": cycle_times(members),
        "estimates": estimate_accuracy(members),
        "priorities": priority_distribution(members),
        "deferrals": deferral_by_label(members),
        "aging": aging_open_items(members),
        "aging_columns": aging_by_priority(members),
        "recent": recent_completions(members),
        "recoveries": recoveries(members),
        "flow": cumulative_flow(members),
        "histogram": throughput_histogram(members),
        "heatmap": completion_heatmap(members),
        "rhythm": completion_rhythm(members),
        "labels": label_distribution(members),
    }
