"""
Materialising a task's recurrence into concrete Instance rows, and closing out
the ones whose moment has gone.

Instances are written ahead of time rather than computed on read, because they
are what the history is made of (docs/Main_App/subsystems/todo.md §3): every
statistic on the Reporting page counts instances, the calendar draws them, and
a retroactive correction edits one. A rule evaluated on the fly would leave
nothing to count, nothing to draw, and nothing to correct.

**How far ahead depends on the kind, and it cannot be otherwise:**

  Fixed    ~90 days. Enough for the month calendar to show a full grid plus
           the reminders that sit ahead of it.
  Rolling  exactly one open instance. "3 days after I last did it" has no
           second date until the first one is done — so there is nothing to
           write. This is visible in the calendar and is worth saying in the
           UI rather than letting it look like a bug.
  One-shot exactly one instance, on its due date.

**How an instance becomes `missed`** — the rule is deliberately derived rather
than stored. An instance is missed once a *later instance of the same task is
already due*: its turn is over because the next turn has arrived. That single
rule gives the right answer for all three kinds without a `window_ends_at`
column that would need recomputing every time a rule changed:

  * a daily task skipped for a week closes six and leaves today's current,
    which is exactly §5's "the board does not grow seven cards";
  * a one-shot task never has a later sibling, so an overdue todo sits on the
    board overdue — it does not quietly become history, which is what a person
    expects of "buy grout" three months later;
  * a rolling task has only ever one open instance, so it likewise stays put
    until it is actually done.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from nora_home.core.signals import item_missed
from nora_home.todo.models import Instance, InstanceOutcome, RecurrenceType, Task, TaskState
from nora_home.todo.recurrence import due_at_on, falls_due_on, fixed_dates, next_rolling_due

logger = logging.getLogger(__name__)

HORIZON_DAYS = 90


def schedulable(queryset=None):
    """Tasks materialisation should act on.

    Archived tasks are excluded on purpose: "not now" means the task goes
    completely quiet (§4), and that has to include its schedule. An archived
    task that kept generating instances would keep accruing misses against
    someone's history for a thing they deliberately put down.
    """
    queryset = Task.objects.all() if queryset is None else queryset
    return queryset.filter(state=TaskState.OPEN, deleted_at__isnull=True)


def current_instance(task) -> Instance | None:
    """The one instance the board shows for this task — the earliest still
    pending. Everything already closed is history; everything later is not its
    turn yet."""
    return task.instances.filter(outcome=InstanceOutcome.PENDING).order_by("due_at").first()


# ── materialisation ──────────────────────────────────────────────────────────

@transaction.atomic
def materialize(task, *, horizon_days: int = HORIZON_DAYS) -> int:
    """Bring `task`'s instances up to date. Returns how many were created.

    Idempotent: safe to call from a save(), from the nightly job, and twice in
    a row.
    """
    if task.state != TaskState.OPEN or task.deleted_at is not None:
        return 0

    if task.recurrence_type == RecurrenceType.NONE:
        return _materialize_one_shot(task)
    if task.recurrence_type == RecurrenceType.ROLLING:
        return _materialize_rolling(task)
    return _materialize_fixed(task, horizon_days=horizon_days)


def _materialize_one_shot(task) -> int:
    """Exactly one instance, on the due date.

    A task with no due date gets none at all — `Instance.due_at` is the moment
    this occasion was *for*, and inventing one would put a fabricated date into
    the history every chart is drawn from. Undated tasks still live on the
    board; they simply have nothing dated to record until they are completed,
    and completing one is what creates its instance (Story 31).
    """
    if not task.due_on:
        return 0

    when = due_at_on(task, task.due_on)
    pending = task.instances.filter(outcome=InstanceOutcome.PENDING).order_by("due_at").first()

    if pending is None:
        # Only create if the task has never had an instance at all. Otherwise a
        # completed one-shot task would sprout a fresh instance every time this
        # ran, and "done" would never stay done.
        if task.instances.exists():
            return 0
        Instance.objects.create(task=task, due_at=when)
        return 1

    if pending.due_at != when:
        # The task was rescheduled. Move its open instance rather than leaving a
        # stale one and adding a second.
        pending.due_at = when
        pending.save(update_fields=["due_at", "updated_at"])
    return 0


def _materialize_rolling(task) -> int:
    """One open instance, never more. The next date is unknowable until this
    one is completed, so there is nothing further to write."""
    if current_instance(task) is not None:
        return 0

    when = next_rolling_due(task)
    if when is None:
        return 0

    _, created = Instance.objects.get_or_create(task=task, due_at=when)
    return int(created)


def _materialize_fixed(task, *, horizon_days: int) -> int:
    """Drop future instances the rule no longer produces, then fill the window.

    **The order matters and is not arbitrary.** Filling first would compute the
    scan's starting point from an instance that is about to be deleted: change a
    task's due time from 09:00 to 07:00 and the horizon is already full, so
    nothing new is created — then every future 09:00 instance is dropped as
    stale, leaving the task with no schedule at all until the next nightly run.
    Clearing first means the scan starts from what actually survived.
    """
    today = timezone.localdate()
    horizon = today + timedelta(days=horizon_days)

    _drop_stale_future(task)

    latest = (task.instances.order_by("-due_at").values_list("due_at", flat=True).first())
    # With no instances yet, start from yesterday so today's own occasion is
    # picked up by the exclusive `after` bound — and no earlier.
    #
    # **History is never backfilled**, deliberately. A task created today whose
    # rule anchors weeks ago must not conjure a fortnight of occasions that
    # nobody could have done, because `close_passed` would immediately close
    # every one of them as missed and invent a failure that never happened.
    # Instances only ever exist from the moment the task did.
    after = timezone.localtime(latest).date() if latest else today - timedelta(days=1)

    created = 0
    for day in fixed_dates(task, after=after, until=horizon):
        _, was_created = Instance.objects.get_or_create(task=task, due_at=due_at_on(task, day))
        created += int(was_created)
    return created


def _drop_stale_future(task) -> int:
    """Remove still-future pending instances the rule no longer generates.

    Without this, changing "every Monday" to "every Tuesday" leaves 13 phantom
    Mondays on the calendar forever. Only untouched future instances are
    removed — anything already due, already closed, or carrying a comment,
    photo or link a person put there is left alone, because silently deleting
    someone's note to fix a schedule is a much worse bug than a stale row.
    """
    now = timezone.now()
    candidates = task.instances.filter(
        outcome=InstanceOutcome.PENDING, due_at__gt=now,
    ).exclude(comments__isnull=False).exclude(attachments__isnull=False).exclude(
        links__isnull=False).distinct()

    removed = 0
    for instance in candidates:
        day = timezone.localtime(instance.due_at).date()
        # Judged on the day alone. If only the *time* moved — someone changed
        # due_time, or their default hour — the correct instance for that day
        # was just created above, and this one is the leftover.
        if not falls_due_on(task, day) or instance.due_at != due_at_on(task, day):
            instance.delete()
            removed += 1
    return removed


def materialize_open_tasks(*, horizon_days: int = HORIZON_DAYS) -> dict:
    """Every schedulable task, one at a time.

    One task's broken rule must not stop the rest of the house being
    scheduled — a spec someone typed by hand in the admin is exactly the kind
    of thing that fails here, and it should cost that task its schedule, not
    everyone's.
    """
    created = 0
    failed = 0
    for task in schedulable().iterator():
        try:
            created += materialize(task, horizon_days=horizon_days)
        except Exception:
            failed += 1
            logger.exception("Could not materialize todo task %s", task.pk)
    if created or failed:
        logger.info("Todo materialisation: %s created, %s failed", created, failed)
    return {"created": created, "failed": failed}


# ── closing out what has gone past ───────────────────────────────────────────

def close_passed_instances(*, now=None, limit: int = 2000) -> dict:
    """Mark as `missed` every pending instance whose turn is over.

    An instance's turn is over when a later instance of the same task is
    already due — see this module's docstring for why that is the whole rule.
    Fires `nora_home.core.signals.item_missed` for each, so anything that wants
    to react to a miss can, without importing this app.
    """
    now = now or timezone.now()

    passed = list(
        Instance.objects
        .filter(outcome=InstanceOutcome.PENDING, due_at__lte=now,
                task__state=TaskState.OPEN, task__deleted_at__isnull=True)
        .select_related("task", "task__owner")
        .order_by("task_id", "due_at")[:limit]
    )

    # Group by task and keep the newest of each — that one is the task's
    # current turn and is legitimately still open, however overdue it looks.
    by_task: dict[int, list[Instance]] = {}
    for instance in passed:
        by_task.setdefault(instance.task_id, []).append(instance)

    missed = 0
    for instances in by_task.values():
        for instance in instances[:-1]:
            instance.outcome = InstanceOutcome.MISSED
            instance.save(update_fields=["outcome", "updated_at"])
            item_missed.send(sender=Instance, item=instance,
                             member=instance.task.owner, due_at=instance.due_at)
            missed += 1

    if missed:
        logger.info("Closed %s todo instances as missed", missed)
    return {"missed": missed}
