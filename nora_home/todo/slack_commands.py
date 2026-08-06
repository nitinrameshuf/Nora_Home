"""
What `/todo` means, and what the buttons on a reminder do
(docs/Main_App/subsystems/todo.md §12).

**One command with subcommands, not four commands.** Decided 2026-08-06: Slack
only has to be told about `/todo`, everything routes through one handler, and a
future action is a new branch here rather than new configuration in the Slack
app. The cost is Slack's per-command autocomplete hint, which `/todo help`
replaces.

**Every action goes through `nora_home.todo.api`.** Not through the models, and
not through the views: the api is where permission checks, the approval
transitions and the change trail live, so Slack gets exactly the same rules the
board does and cannot become a back door that skips them. When the api raises,
the message the person sees is the api's own — those are already written for a
human.

Identification is deliberately implicit. Nobody is going to type a UUID on a
phone, so `ack` and `approve` act on *your* most pressing item and say which
one they picked. `list` exists so that is never a guess.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from uuid import UUID

from django.core.exceptions import PermissionDenied, ValidationError
from django.utils import timezone

from nora_home.notifications.slack_commands import action, command
from nora_home.todo import api
from nora_home.todo.models import (
    Instance,
    InstanceOutcome,
    Priority,
    Reminder,
    Task,
    TaskSource,
    TaskState,
)
from nora_home.todo.reminders import ensure_default_reminder
from nora_home.todo.scheduling import materialize

logger = logging.getLogger(__name__)

SNOOZE_MINUTES = 30

HELP = (
    "*What I understand*\n"
    "• `/todo` or `/todo list` — what's open for you\n"
    "• `/todo new <title>` — add a task to your board\n"
    "• `/todo ack` — acknowledge the most overdue thing, without claiming it's done\n"
    "• `/todo approve` — approve the oldest thing waiting on you\n"
    "• `/todo reject <reason>` — send it back, with a reason (required)\n"
    "• `/todo help` — this"
)


# ── the slash command ────────────────────────────────────────────────────────

@command("/todo")
def handle_todo(member, text: str) -> str:
    """`/todo <subcommand> [args]`. A bare `/todo` lists, because that is what
    someone reaching for it on a phone almost always wants."""
    parts = text.split(maxsplit=1)
    subcommand = parts[0].lower() if parts else "list"
    rest = parts[1].strip() if len(parts) > 1 else ""

    handler = {
        "list": _list,
        "new": _new,
        "add": _new,          # the word half the house will reach for first
        "ack": _ack,
        "approve": _approve,
        "reject": _reject,
        "help": lambda *_: HELP,
    }.get(subcommand)

    if handler is None:
        return f"I don't know `{subcommand}`.\n\n{HELP}"
    return handler(member, rest)


def _list(member, _rest: str) -> str:
    instances = _open_instances(member)[:10]
    if not instances:
        return "Nothing open. Enjoy it."

    lines = []
    now = timezone.now()
    for instance in instances:
        when = timezone.localtime(instance.due_at)
        late = " *overdue*" if instance.due_at < now else ""
        lines.append(f"• {instance.task.title} — {when:%a %d %b, %H:%M}{late}")

    waiting = _awaiting_my_approval(member).count()
    if waiting:
        lines.append(f"\n_{waiting} waiting on your approval — `/todo approve`_")
    return "\n".join(lines)


def _new(member, rest: str) -> str:
    title = rest.strip()
    if not title:
        return "What should it be called? `/todo new Take the bins out`"

    task = Task.objects.create(title=title[:200], owner=member, priority=Priority.P2)
    # No due date, deliberately: guessing one would put a fabricated deadline
    # into the history every chart is drawn from (§3). It lands on the board in
    # Priority 2 and someone can date it there.
    materialize(task)
    ensure_default_reminder(task)
    logger.info("Task created from Slack by %s: %s", member, title[:80])
    return f"Added *{task.title}* to your board, Priority 2, no due date yet."


def _ack(member, _rest: str) -> str:
    instance = _open_instances(member).filter(due_at__lt=timezone.now()).first()
    if instance is None:
        return "Nothing overdue to acknowledge."

    api.acknowledge(instance, member=member)
    return (f"Acknowledged *{instance.task.title}* — the escalation stops, the "
            f"task stays open.")


def _approve(member, _rest: str) -> str:
    instance = _awaiting_my_approval(member).first()
    if instance is None:
        return "Nothing is waiting on your approval."

    try:
        api.approve(instance, member=member)
    except (PermissionDenied, ValidationError) as exc:
        return _humanise(exc)
    return f"Approved *{instance.task.title}*."


def _reject(member, rest: str) -> str:
    reason = rest.strip()
    if not reason:
        # §4a makes the reason mandatory, and this is the one place a person
        # could plausibly try to skip it.
        return "A rejection needs a reason: `/todo reject not cleaned properly`"

    instance = _awaiting_my_approval(member).first()
    if instance is None:
        return "Nothing is waiting on your approval."

    try:
        api.reject(instance, member=member, reason=reason)
    except (PermissionDenied, ValidationError) as exc:
        return _humanise(exc)
    return f"Sent *{instance.task.title}* back: “{reason}”"


# ── the buttons on a reminder ────────────────────────────────────────────────

@action("todo_done")
def button_done(member, value: str) -> str:
    instance = _instance_from(value)
    if instance is None:
        return "That task is no longer there."

    try:
        instance = api.complete(instance, member=member)
    except (PermissionDenied, ValidationError) as exc:
        return _humanise(exc)

    if instance.outcome == InstanceOutcome.AWAITING_APPROVAL:
        approver = instance.task.approver
        return (f"✓ *{instance.task.title}* — sent to "
                f"{approver.name if approver else 'the approver'} to approve.")
    return f"✓ *{instance.task.title}* — done, by {member.name}."


@action("todo_skip")
def button_skip(member, value: str) -> str:
    instance = _instance_from(value)
    if instance is None:
        return "That task is no longer there."

    try:
        api.skip(instance, member=member, reason="Skipped from Slack")
    except (PermissionDenied, ValidationError) as exc:
        return _humanise(exc)
    # §5: a skip declared before the due moment is a decision, not a failure —
    # worth saying, since the button sits next to "Done" and should not feel
    # like an admission.
    return f"*{instance.task.title}* — skipped. That's a decision, not a miss."


@action("todo_snooze")
def button_snooze(member, value: str) -> str:
    """Remind again shortly. Deliberately *not* a change of due date: moving the
    deadline would write a deferral into the change trail that
    `analytics.deferral_by_label()` reads, and "remind me after dinner" is not
    the same claim as "this is now due tomorrow"."""
    instance = _instance_from(value)
    if instance is None:
        return "That task is no longer there."

    when = timezone.now() + timedelta(minutes=SNOOZE_MINUTES)
    Reminder.objects.create(task=instance.task, absolute_at=when,
                            channels=["slack"])
    local = timezone.localtime(when)
    return f"*{instance.task.title}* — back at {local:%H:%M}."


@action("todo_reassign")
def button_reassign(member, value: str) -> str:
    """`value` is `<instance uuid>|<member pk>`, from the select's chosen option."""
    instance_ref, _, member_ref = value.partition("|")
    instance = _instance_from(instance_ref)
    if instance is None:
        return "That task is no longer there."

    from nora_home.accounts.models import HouseMember

    if not member_ref.isdigit():
        return "I don't recognise that person."
    new_owner = HouseMember.objects.filter(pk=int(member_ref), is_active=True).first()
    if new_owner is None:
        return "I don't recognise that person."

    task = instance.task
    before = api.snapshot(task)
    task.owner = new_owner
    task.save(update_fields=["owner", "updated_at"])
    api.record_changes(task, before, actor=member)
    return f"*{task.title}* — now {new_owner.name}'s."


# ── helpers ──────────────────────────────────────────────────────────────────

def _open_instances(member):
    """This person's live occasions, soonest first. Scoped through
    `api.tasks_for`, so "mine" means the same here as everywhere else — owned
    or assigned, never someone else's board."""
    return (Instance.objects
            .filter(task__in=api.tasks_for([member],
                                           queryset=Task.objects.alive().filter(
                                               state=TaskState.OPEN,
                                               source=TaskSource.USER)),
                    outcome=InstanceOutcome.PENDING)
            .select_related("task")
            .order_by("due_at"))


def _awaiting_my_approval(member):
    return (Instance.objects
            .filter(task__approver=member, task__deleted_at__isnull=True,
                    outcome=InstanceOutcome.AWAITING_APPROVAL)
            .select_related("task")
            .order_by("due_at"))


def _instance_from(value: str):
    """A malformed uuid is a `ValidationError` out of the query itself, not a
    miss — so a stale button from an old message, or anything else Slack hands
    back, has to be caught here rather than becoming a 500 in a socket thread."""
    if not value:
        return None
    try:
        uuid = UUID(value)
    except (TypeError, ValueError):
        logger.warning("Slack sent an unusable instance reference: %r", value[:80])
        return None
    return (Instance.objects.select_related("task", "task__approver")
            .filter(uuid=uuid, task__deleted_at__isnull=True)
            .first())


def _humanise(exc) -> str:
    """The api's own wording. It is already written for a person — repeating it
    here in different words would give the board and Slack two vocabularies for
    the same rule."""
    return exc.messages[0] if hasattr(exc, "messages") else str(exc)
