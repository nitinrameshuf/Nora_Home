"""
Turning a `Reminder` row into an actual notification, and giving a task with a
due date one automatically (docs/Main_App/subsystems/todo.md §8).

**Reminders help; escalation chases.** This module only ever fires *before or
at* the due moment, to whoever is doing the work. It never nags — one reminder
per due occasion, ever — and it never widens the audience over time; that
climbing behaviour is `nora_home.todo.escalation`'s job, not this one's.

Event reminders (the `Reminder.event` side of the model) are deliberately not
evaluated here yet. A recurring event's *next* occurrence needs the same
calendar arithmetic Story 33 (Calendar) is going to build anyway — writing a
second, narrower version of it here just to unblock reminders would be the
kind of thing that quietly drifts from the real one once Calendar lands.
"""

from __future__ import annotations

import logging
from datetime import timedelta

from django.utils import timezone

from nora_home.notifications.api import notify, notify_house
from nora_home.todo import api
from nora_home.todo.models import (
    Instance,
    InstanceOutcome,
    Priority,
    Reminder,
    Task,
    TaskState,
)

logger = logging.getLogger(__name__)

# A reminder is meant to fire exactly once, ever, for its instance. The dedupe
# window only has to outlast the gap between scans (5 minutes) plus however
# long a due date might be set in the future — 30 days is generous for any
# realistic reminder offset without risking a *legitimate* second send for the
# same instance being mistaken for a repeat.
REMINDER_DEDUPE_MINUTES = 60 * 24 * 30

# §8 "Routing by priority" — reminders only. Escalation's own, wider table
# lives in nora_home.todo.escalation.
REMINDS_THE_HOUSE_TOO = {Priority.P1}

# "sound" is handled separately from every other channel — see
# `_queue_alarms()` — because it needs a house-wide backlog rule (§10.4) the
# per-recipient notify() loop below has no way to apply. Filtered out here so
# it is never passed straight through as an ordinary channel.
ALARM_CHANNEL = "sound"


def ensure_default_reminder(task: Task) -> Reminder | None:
    """§8: "A task given a due date gets a reminder automatically." Only fills
    a gap — a task that already has any reminder of its own, or one added
    later, is never overridden or duplicated."""
    if not task.due_on or task.reminders.exists():
        return None
    return Reminder.objects.create(task=task, offset_minutes=0)


def fire_at(reminder: Reminder, due_at):
    """When this reminder is meant to go off for an occasion due at `due_at`.

    `absolute_at` wins when set — it only makes sense on a non-recurring task
    in the first place (enforced where reminders are scheduled, per the
    model's own docstring, which is here). Otherwise it's relative: minutes
    before the due moment.
    """
    if reminder.absolute_at:
        return reminder.absolute_at
    if reminder.offset_minutes is not None:
        return due_at - timedelta(minutes=reminder.offset_minutes)
    return None


def send_due_reminders(*, now=None, limit: int = 500) -> dict:
    """Fire every reminder whose moment has arrived for a still-pending
    occasion. Safe to run every few minutes — each (instance, reminder) pair
    fires at most once, via notify()'s own dedupe_key mechanism, which is what
    the build brief points at rather than a bespoke "sent" flag.
    """
    now = now or timezone.now()

    reminders = (Reminder.objects
                 .filter(task__isnull=False, task__state=TaskState.OPEN,
                        task__deleted_at__isnull=True)
                 .select_related("task", "task__owner")
                 .prefetch_related("task__assignees")[:limit])

    due = []
    for reminder in reminders:
        task = reminder.task
        instance = task.instances.filter(outcome=InstanceOutcome.PENDING).order_by("due_at").first()
        if instance is None:
            continue

        when = fire_at(reminder, instance.due_at)
        if when is None or when > now:
            continue
        due.append((task, instance, reminder))

    sent = 0
    for task, instance, reminder in due:
        try:
            if _send_reminder(task, instance, reminder):
                sent += 1
        except Exception:
            logger.exception("Reminder failed for task %s", task.pk)

    _queue_alarms(due)

    if sent:
        logger.info("Sent %s todo reminders", sent)
    return {"sent": sent}


def _queue_alarms(due: list[tuple[Task, Instance, Reminder]]) -> None:
    """§10.4, "backlog after downtime": if the Pi was off, or several alarms
    simply land in the same sweep, play only the most recent and collapse the
    rest into one message rather than firing every sound in a burst.

    A house has one set of speakers, so this is a house-wide decision made
    once per sweep — unlike everything in `_send_reminder()`, which fans out
    per recipient.
    """
    from nora_home.todo.alarms import queue_alarm, queue_missed_alarms_summary

    # Gated on the task's own alarm_kind alone, not on a reminder's channels
    # list — there is no UI anywhere that lets a person put "sound" into a
    # Reminder.channels, so requiring it would make a task's alarm form field
    # do nothing. §10.1 frames the alarm as the task's own property; a
    # reminder here is only the trigger for *when*.
    seen_tasks = set()
    eligible = []
    for task, instance, _reminder in due:
        if task.alarm_kind and task.pk not in seen_tasks:
            seen_tasks.add(task.pk)
            eligible.append((task, instance))
    if not eligible:
        return

    eligible.sort(key=lambda pair: pair[1].due_at)
    *backlog, (latest_task, latest_instance) = eligible
    queue_alarm(latest_task, latest_instance)
    if backlog:
        queue_missed_alarms_summary([task for task, _ in backlog])


def _slack_actions(task: Task, instance) -> list[dict]:
    """Done · Skip · Snooze · Reassign, for the Slack message itself (§12).

    Answering a reminder from a phone should not mean opening the house — that
    is the whole point of the buttons, and better than typing a slash command
    one-handed. Handlers live in `nora_home.todo.slack_commands`; the
    `action_id`s here are the contract between the two.
    """
    from nora_home.accounts.models import HouseMember

    others = HouseMember.objects.filter(is_active=True).exclude(pk=task.owner_id)
    actions = [
        {"action_id": "todo_done", "text": "Done", "value": str(instance.uuid),
         "style": "primary"},
    ]

    # Skip only while it is still a *decision*. §5 draws the line at the due
    # moment: before it, declining is deliberate and excluded from miss
    # patterns; after it, the occasion is already a miss and `api.skip` refuses.
    # Since the default reminder fires exactly at `due_at`, this button would
    # otherwise be present and broken on almost every reminder the house sends
    # — offering it is only honest when it can still work.
    if instance.due_at > timezone.now():
        actions.append({"action_id": "todo_skip", "text": "Skip",
                        "value": str(instance.uuid)})

    actions.append({"action_id": "todo_snooze", "text": "Snooze",
                    "value": str(instance.uuid)})
    if others.exists():
        # A select rather than a button: reassigning needs a *target*, and a
        # button cannot carry one without a modal round trip.
        actions.append({
            "action_id": "todo_reassign", "text": "Reassign",
            "options": [{"text": member.name, "value": f"{instance.uuid}|{member.pk}"}
                        for member in others],
        })
    return actions


def _send_reminder(task: Task, instance, reminder: Reminder) -> bool:
    # "sound" is handled house-wide by _queue_alarms(), not per recipient here
    # — passing it through to notify() would fan an alarm out to every
    # assignee individually, which is not what one set of speakers means.
    channels = [c for c in (reminder.channels or []) if c != ALARM_CHANNEL] or None
    recipients = api.doers(task)
    key = f"todo-reminder:{instance.uuid}:{reminder.pk}"
    actions = _slack_actions(task, instance)

    any_sent = False
    for member in recipients:
        result = notify(
            member, title=f"Due: {task.title}",
            body=f"Due {timezone.localtime(instance.due_at):%a %d %b, %H:%M}.",
            severity="info", app_slug="todo", url=f"/todo/t/{task.uuid}/",
            dedupe_key=f"{key}:{member.pk}", dedupe_minutes=REMINDER_DEDUPE_MINUTES,
            channels=channels, slack_actions=actions,
        )
        any_sent = any_sent or result is not None

    if task.priority in REMINDS_THE_HOUSE_TOO:
        result = notify_house(
            title=f"Due: {task.title}",
            body=f"{task.owner.name} — due {timezone.localtime(instance.due_at):%a %d %b, %H:%M}.",
            severity="info", app_slug="todo", url=f"/todo/t/{task.uuid}/",
            dedupe_key=f"{key}:house", dedupe_minutes=REMINDER_DEDUPE_MINUTES,
            channels=["slack"],
        )
        any_sent = any_sent or result is not None

    return any_sent
