"""
Turning a Reminder row into an actual notification (docs/Main_App/subsystems/
todo.md §8). Reminders only ever fire before or at the due moment, to whoever
is doing the work, exactly once — the three properties this file checks most
carefully, because a reminder that nags is worse than one that says nothing.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from django.utils import timezone

from nora_home.notifications.models import Notification
from nora_home.todo.models import Priority, Reminder, Task
from nora_home.todo.reminders import (
    REMINDER_DEDUPE_MINUTES,
    ensure_default_reminder,
    fire_at,
    send_due_reminders,
)
from nora_home.todo.scheduling import current_instance, materialize

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def make_task(member):
    """Every task here pins `due_time` to midnight, and that is load-bearing.

    A task with a due date and no time falls due at the per-member default hour
    — 09:00 (`recurrence.FALLBACK_DUE_HOUR`). So a task due *today* has not
    actually come due until 09:00 today, and every test asserting that a
    reminder fires would fail for anyone running the suite between midnight and
    breakfast. That is not hypothetical: it failed on the Pi at 00:07, and the
    identical code passed when only the timezone was shifted so "now" was
    10:09. CLAUDE.md's claim that this suite "gives the same answer on a laptop
    and on the Pi" has to mean at any hour, too.

    Midnight rather than a time computed from `now`, because a fixed value is
    the thing that makes the test read the same at 3am as at 3pm.
    """
    def _make(**kwargs):
        kwargs.setdefault("due_time", time(0, 0))
        kwargs.setdefault("title", "A thing")
        kwargs.setdefault("owner", member)
        kwargs.setdefault("priority", Priority.P2)
        return Task.objects.create(**kwargs)

    return _make


# ── the automatic default reminder ───────────────────────────────────────────

def test_a_task_with_a_due_date_gets_a_reminder_automatically(make_task):
    task = make_task(due_on=TODAY)

    reminder = ensure_default_reminder(task)

    assert reminder is not None
    assert task.reminders.count() == 1
    assert reminder.offset_minutes == 0


def test_a_task_with_no_due_date_gets_no_reminder(make_task):
    task = make_task()

    assert ensure_default_reminder(task) is None
    assert task.reminders.count() == 0


def test_an_existing_reminder_is_never_duplicated(make_task):
    task = make_task(due_on=TODAY)
    ensure_default_reminder(task)

    assert ensure_default_reminder(task) is None
    assert task.reminders.count() == 1


def test_a_reminder_someone_set_up_themselves_is_never_overridden(make_task):
    """The default only fills a gap — it never second-guesses a person's own
    choice, even one offset differently from what the default would pick."""
    task = make_task(due_on=TODAY)
    Reminder.objects.create(task=task, offset_minutes=120)

    assert ensure_default_reminder(task) is None
    assert task.reminders.get().offset_minutes == 120


# ── when a reminder fires ────────────────────────────────────────────────────

def test_a_relative_offset_counts_backward_from_due(make_task):
    task = make_task(due_on=TODAY)
    reminder = Reminder.objects.create(task=task, offset_minutes=30)
    due_at = timezone.now()

    assert fire_at(reminder, due_at) == due_at - timedelta(minutes=30)


def test_an_absolute_time_wins_over_any_offset(make_task):
    task = make_task(due_on=TODAY)
    absolute = timezone.now() - timedelta(days=1)
    reminder = Reminder.objects.create(task=task, offset_minutes=30, absolute_at=absolute)

    assert fire_at(reminder, timezone.now()) == absolute


def test_neither_offset_nor_absolute_produces_nothing_to_fire(make_task):
    task = make_task(due_on=TODAY)
    reminder = Reminder.objects.create(task=task, offset_minutes=None)

    assert fire_at(reminder, timezone.now()) is None


# ── sending ───────────────────────────────────────────────────────────────────

def test_a_reminder_whose_moment_has_arrived_sends(make_task, member):
    task = make_task(due_on=TODAY, priority=Priority.P2)
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0)

    result = send_due_reminders()

    assert result["sent"] == 1
    assert Notification.objects.filter(recipient=member, app_slug="todo").exists()


def test_nothing_fires_before_its_moment(make_task, member):
    task = make_task(due_on=TODAY + timedelta(days=5), priority=Priority.P2)
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0)

    result = send_due_reminders()

    assert result["sent"] == 0
    assert not Notification.objects.exists()


def test_a_reminder_fires_at_most_once(make_task, member):
    """Repeated sweeps must not turn one reminder into nagging."""
    task = make_task(due_on=TODAY, priority=Priority.P2)
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0)

    send_due_reminders()
    send_due_reminders()
    send_due_reminders()

    assert Notification.objects.filter(recipient=member).count() == 1


def test_a_task_already_completed_gets_no_reminder(make_task, member):
    task = make_task(due_on=TODAY, priority=Priority.P2)
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0)
    from nora_home.todo import api
    api.complete(current_instance(task), member=member)

    result = send_due_reminders()

    assert result["sent"] == 0


def test_an_archived_tasks_reminder_produces_nothing(make_task, member):
    from nora_home.todo.models import TaskState

    task = make_task(due_on=TODAY, priority=Priority.P2, state=TaskState.ARCHIVED)
    Reminder.objects.create(task=task, offset_minutes=0)

    result = send_due_reminders()

    assert result["sent"] == 0


def test_the_reminder_dedupe_window_is_generous(make_task):
    """A month is comfortably longer than any realistic offset, so a Pi that
    was briefly down never gets a legitimate reminder wrongly suppressed."""
    assert REMINDER_DEDUPE_MINUTES >= 60 * 24 * 7


# ── routing by priority (§8) ─────────────────────────────────────────────────

def test_priority_one_also_reaches_the_family_channel(make_task, member):
    task = make_task(due_on=TODAY, priority=Priority.P1)
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0)

    send_due_reminders()

    assert Notification.objects.filter(recipient=None, app_slug="todo").exists()
    assert Notification.objects.filter(recipient=member, app_slug="todo").exists()


@pytest.mark.parametrize("priority", [Priority.P2, Priority.P3])
def test_lower_priorities_stay_personal(make_task, member, priority):
    task = make_task(due_on=TODAY, priority=priority)
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0)

    send_due_reminders()

    assert Notification.objects.filter(recipient=member).exists()
    assert not Notification.objects.filter(recipient=None).exists()


def test_a_shared_task_reminds_every_assignee(make_task, make_member):
    bob, carol = make_member("bob"), make_member("carol")
    task = make_task(due_on=TODAY, priority=Priority.P2)
    task.assignees.set([bob, carol])
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0)

    send_due_reminders()

    assert Notification.objects.filter(recipient=bob).exists()
    assert Notification.objects.filter(recipient=carol).exists()


def test_a_sound_channel_choice_is_dropped_not_forwarded(make_task, member):
    """Story 38 (Alarms & House Audio) is what actually plays sound; no audio
    plumbing exists anywhere in this codebase yet. Passing "sound" through to
    notify() unfiltered would be a channel it has never heard of."""
    task = make_task(due_on=TODAY, priority=Priority.P2)
    materialize(task)
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=0, channels=["sound"])

    result = send_due_reminders()

    notification = Notification.objects.get(recipient=member)
    assert not notification.deliveries.filter(channel="sound").exists()
    assert result["sent"] == 1
