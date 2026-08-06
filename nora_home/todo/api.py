"""
Todo's published API — the functions the rest of the house calls instead of
importing `nora_home.todo.models`. See CLAUDE.md §6 ("Never import another app's
models") and docs/Main_App/cross-functionality.md.

This module owns **one instance's journey through its outcomes**, plus the two
things sharing a task with other people changes about the rest of the system:
who a task is visible to, and how much of its effort lands on each person.

The transitions (docs/Main_App/subsystems/todo.md §4a):

    pending ──complete──▶ awaiting_approval ──approve──▶ done
                                 │
                                 └──reject (reason required)──▶ pending

With no approver, `complete` goes straight to `done`. That is the same call
either way — a caller never has to ask which kind of task it is holding, which
is the whole reason the approver's *presence* is the requirement rather than a
separate mode flag.
"""

from __future__ import annotations

import logging

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from nora_home.core.signals import item_completed
from nora_home.todo.models import ChangeEvent, Instance, InstanceOutcome, Task, TaskState

logger = logging.getLogger(__name__)

# ChangeEvent.field for the approval trail. One field name for the whole cycle
# so a task's approval history is a single ordered query, with to_value saying
# which step it was.
APPROVAL = "approval"


# ── who a task belongs to ────────────────────────────────────────────────────

def doers(task) -> list:
    """The people who actually do this task.

    Assignees when there are any; otherwise the owner alone. `owner` means
    *responsible* and `assignees` means *can do it* (§4a), so a task handed to
    Bob and Carol is Bob and Carol's work even though Alice is the one
    escalation chases. This is also the set the effort splits across.
    """
    assigned = list(task.assignees.all())
    return assigned if assigned else [task.owner]


def can_complete(task, member) -> bool:
    """Any assignee closes it — the first person to finish it finishes it. The
    owner can always close their own task, whoever else it is shared with."""
    if member is None:
        return False
    if task.owner_id == member.pk:
        return True
    return task.assignees.filter(pk=member.pk).exists()


def tasks_for(members, *, queryset=None):
    """Tasks belonging to these people: `owner in members OR assignees
    intersects members`.

    **`.distinct()` is not optional here.** The M2M join produces one row per
    matching assignee, so a task shared by three people whose board is being
    built for all three would render three identical cards — a bug that looks
    like a rendering fault and gets debugged in the template for an hour.

    Soft-deleted tasks are excluded by default, because no board ever means to
    show them and `Task.objects` does not filter them for you. *Archived* tasks
    are not excluded — "not now" is a column on the board (§4), not a deletion.
    Pass an explicit `queryset` to scope some other set; a caller who has
    already chosen what to scope is not second-guessed.
    """
    ids = _member_ids(members)
    queryset = Task.objects.alive() if queryset is None else queryset
    if not ids:
        return queryset.none()
    return queryset.filter(Q(owner_id__in=ids) | Q(assignees__id__in=ids)).distinct()


def _member_ids(members) -> list:
    """Accept one member or many, model instances or ids. Call sites vary, and
    every one of them getting this wrong differently is worse than one helper."""
    if members is None:
        return []
    if not isinstance(members, (list, tuple, set, frozenset)):
        members = [members]
    return [getattr(m, "pk", m) for m in members if m is not None]


# ── effort ───────────────────────────────────────────────────────────────────

def effort_share_minutes(instance, member=None) -> float | None:
    """How many minutes this occasion adds to **one person's** load.

    **Effort splits, it never multiplies.** A 60-minute task shared by three
    people is 20 minutes each. Counting it in full three times would tell three
    people they each have a full day of what is really one hour of house work,
    and Story 35's scheduling suggestions are built directly on this number, so
    the distortion would propagate into the advice people are given.

    `None` when the duration is unknown — that is different from zero, and a
    load calculation should be able to tell "no estimate" from "no work".
    Passing a `member` who is not one of the task's `doers()` gives 0.0.
    """
    total = instance.effective_minutes
    if total is None:
        return None

    sharers = doers(instance.task)
    if member is not None and not any(d.pk == member.pk for d in sharers):
        return 0.0
    return total / len(sharers)


# ── the transitions ──────────────────────────────────────────────────────────

@transaction.atomic
def complete(instance, *, member, actual_minutes=None, note=None, at=None) -> Instance:
    """Finish one occasion.

    Lands on `done`, or on `awaiting_approval` when the task has an approver.
    Callers do not branch on which.

    `at` exists because completion is retroactively editable (§4): ticking last
    Monday's instance on Wednesday records Monday's work, and must not disturb
    Wednesday's own row.
    """
    task = instance.task
    if not can_complete(task, member):
        raise PermissionDenied(
            f"{member} is neither the owner nor an assignee of {task!r}")
    if instance.outcome == InstanceOutcome.AWAITING_APPROVAL:
        raise ValidationError("That occasion is already waiting on its approver.")

    # Completing a `missed` day is a legitimate retroactive correction (§4), and
    # so is amending an already-done one — but only the first is a *transition*,
    # and only a transition should be announced. Without this, editing the note
    # on last week's completion re-fires item_completed and a receiver says
    # "nice one" in Slack about work finished days ago.
    already_done = instance.outcome == InstanceOutcome.DONE

    # On an amendment, *when* and *who* stay as they were. Correcting the note on
    # last week's completion must not restamp it as finished today by whoever is
    # doing the correcting — the history every chart is drawn from would drift a
    # little further from the truth with each edit. An explicit `at` still wins,
    # which is how a genuine retroactive correction of the time is made.
    if at is not None or not already_done:
        instance.completed_at = at or timezone.now()
        instance.completed_by = member
    if actual_minutes is not None:
        instance.actual_minutes = actual_minutes
    if note is not None:
        instance.note = note

    if task.needs_approval:
        instance.outcome = InstanceOutcome.AWAITING_APPROVAL
        instance.save(update_fields=["outcome", "completed_at", "completed_by",
                                     "actual_minutes", "note", "updated_at"])
        _record(instance, member=member, step="submitted")
        # Deliberately no item_completed here. Nothing has been completed yet as
        # far as the rest of the house is concerned, and firing it now would let
        # a receiver celebrate work the approver is about to send back.
        return instance

    instance.outcome = InstanceOutcome.DONE
    instance.save(update_fields=["outcome", "completed_at", "completed_by",
                                 "actual_minutes", "note", "updated_at"])
    if not already_done:
        _finish_task_if_one_shot(task)
        _announce_completion(instance)
    return instance


@transaction.atomic
def approve(instance, *, member, at=None) -> Instance:
    """The approver says yes. Only then is it done."""
    _require_approver(instance, member)
    if instance.outcome != InstanceOutcome.AWAITING_APPROVAL:
        raise ValidationError(
            f"Only an occasion awaiting approval can be approved; this one is "
            f"{instance.get_outcome_display().lower()}.")

    instance.outcome = InstanceOutcome.DONE
    instance.approved_at = at or timezone.now()
    instance.approved_by = member
    instance.save(update_fields=["outcome", "approved_at", "approved_by", "updated_at"])
    _record(instance, member=member, step="approved")
    _finish_task_if_one_shot(instance.task)
    _announce_completion(instance)
    return instance


@transaction.atomic
def skip(instance, *, member, reason: str = "", at=None) -> Instance:
    """Mark an occasion skipped — deliberately not done, before its moment
    passed. Once `due_at` has gone, the occasion is a miss instead (§5); the
    board and `close_passed_instances` are what turn a lapsed pending instance
    into `missed`, not this function.
    """
    task = instance.task
    if not can_complete(task, member):
        raise PermissionDenied(
            f"{member} is neither the owner nor an assignee of {task!r}")
    if instance.outcome != InstanceOutcome.PENDING:
        raise ValidationError(
            f"Only a pending occasion can be skipped; this one is "
            f"{instance.get_outcome_display().lower()}.")

    when = at or timezone.now()
    if when > instance.due_at:
        raise ValidationError(
            "That occasion's due moment has already passed — it is a miss "
            "now, not something that can still be skipped (see §5).")

    instance.outcome = InstanceOutcome.SKIPPED
    instance.skipped_at = when
    if reason:
        instance.note = reason
    instance.save(update_fields=["outcome", "skipped_at", "note", "updated_at"])
    _finish_task_if_one_shot(task)
    return instance


@transaction.atomic
def uncomplete(instance, *, member) -> Instance:
    """Undo a tick. Back to `pending`, whether it was `done` or still
    `awaiting_approval` — the person who finished it (or the approver who
    signed off) is allowed to say "actually, not yet".
    """
    task = instance.task
    allowed = can_complete(task, member) or (
        member is not None and task.approver_id == member.pk)
    if not allowed:
        raise PermissionDenied(
            f"{member} has no standing to undo {task!r}'s completion")
    if instance.outcome not in (InstanceOutcome.DONE, InstanceOutcome.AWAITING_APPROVAL):
        raise ValidationError(
            f"Only a done or awaiting-approval occasion can be undone; this "
            f"one is {instance.get_outcome_display().lower()}.")

    instance.outcome = InstanceOutcome.PENDING
    instance.completed_at = None
    instance.completed_by = None
    instance.approved_at = None
    instance.approved_by = None
    instance.save(update_fields=["outcome", "completed_at", "completed_by",
                                 "approved_at", "approved_by", "updated_at"])
    _reopen_task_if_one_shot(task)
    return instance


@transaction.atomic
def reject(instance, *, member, reason: str) -> Instance:
    """The approver says no, and says why.

    **The reason is required, not optional.** "No" with no reason is the thing
    that makes an approval workflow resented — the person who did the work is
    left guessing at what to change. It is stored as a `ChangeEvent`, so it
    lands in the same history as every other change and needs no new table.
    """
    _require_approver(instance, member)
    if instance.outcome != InstanceOutcome.AWAITING_APPROVAL:
        raise ValidationError(
            f"Only an occasion awaiting approval can be rejected; this one is "
            f"{instance.get_outcome_display().lower()}.")
    reason = (reason or "").strip()
    if not reason:
        raise ValidationError({"reason": "Say why — a rejection without a reason "
                                         "leaves the person guessing."})

    instance.outcome = InstanceOutcome.PENDING
    # Cleared because they are no longer true: this occasion is open again. The
    # trail of who submitted it and when survives as ChangeEvents, so nothing is
    # lost by keeping the columns honest.
    instance.completed_at = None
    instance.completed_by = None
    # `note` and `actual_minutes` are deliberately kept. They are the worker's
    # own record, and silently deleting what someone typed because a third party
    # said no is precisely the behaviour §4a warns about.
    instance.save(update_fields=["outcome", "completed_at", "completed_by", "updated_at"])
    _record(instance, member=member, step="rejected", reason=reason)
    return instance


def approval_history(instance):
    """Every submit/approve/reject on this occasion, newest first — which is
    what makes a rejection's reason retrievable at the point it matters."""
    return instance.changes.filter(field=APPROVAL)


# ── the edit trail ───────────────────────────────────────────────────────────
#
# §3 promises that "every reschedule, priority change, label change, skip, and
# archive is its own dated row." §13 says why in one line: **the expensive
# mistake is not the code, it is data thrown away.** `times_moved: 11` cannot
# be turned back into *when* each move happened or what else was going on;
# eleven dated rows can always be turned into an 11.
#
# Nothing writes these except a caller that snapshots first and records after,
# which is deliberate — a signal on Task.save() would fire for every
# materialisation touch and every escalation bookkeeping write too, and the
# trail would be mostly noise.

TRACKED = ("due_on", "priority", "state", "labels")


def snapshot(task) -> dict:
    """What `record_changes()` compares against. Take one *before* saving an
    edit, pass it back afterwards."""
    return {
        "due_on": task.due_on.isoformat() if task.due_on else None,
        "priority": task.priority,
        "state": task.state,
        "labels": sorted(label.name for label in task.labels.all()),
    }


def record_changes(task, before: dict, *, actor=None) -> int:
    """Write one dated `ChangeEvent` per field that actually moved. Returns how
    many were written; zero when someone opened the edit form and saved it
    unchanged, which should leave no trace at all."""
    after = snapshot(task)
    written = 0
    for field in TRACKED:
        old, new = before.get(field), after.get(field)
        if old == new:
            continue
        ChangeEvent.objects.create(task=task, actor=actor, field=field,
                                   from_value=old, to_value=new)
        written += 1
    return written


def acknowledge(instance, *, member) -> Instance:
    """Stop the escalation ladder without claiming the work is done — "seen
    it, will get to it" (§9, ported from the tracker's own `Occurrence.
    acknowledge()`). Anyone the escalation reached can silence it: the owner,
    or anyone on their escalation chain who just got pulled in by a widening
    rung, not only the person who happened to be first notified.
    """
    instance.acknowledged_at = timezone.now()
    instance.acknowledged_by = member
    instance.save(update_fields=["acknowledged_at", "acknowledged_by", "updated_at"])
    return instance


# ── helpers ──────────────────────────────────────────────────────────────────

def _finish_task_if_one_shot(task):
    """A one-shot task whose only instance is resolved has nothing left to do
    — §4: "Done — finished, leaves the board, lives in history." A recurring
    task's instances resolve one at a time forever, so it never follows; that
    is `is_recurring`'s whole job here.
    """
    if task.is_recurring or task.state != TaskState.OPEN:
        return
    task.state = TaskState.DONE
    task.save(update_fields=["state", "updated_at"])


def _reopen_task_if_one_shot(task):
    if task.is_recurring or task.state != TaskState.DONE:
        return
    task.state = TaskState.OPEN
    task.save(update_fields=["state", "updated_at"])


def _require_approver(instance, member):
    task = instance.task
    if not task.needs_approval:
        raise ValidationError("That task has no approver — completing it is completing it.")
    if member is None or task.approver_id != member.pk:
        raise PermissionDenied(f"Only {task.approver} can approve this task.")


def _record(instance, *, member, step: str, reason: str = ""):
    ChangeEvent.objects.create(
        task=instance.task, instance=instance, actor=member,
        field=APPROVAL, to_value=step, reason=reason,
    )


def _announce_completion(instance):
    """Fires once, at the moment the occasion genuinely becomes done — on
    `complete()` for an ordinary task, on `approve()` for one with an approver.

    `completion` carries the instance itself: unlike the tracker, Todo has no
    separate Completion row, because the instance already holds the note and the
    actual minutes a receiver would want.
    """
    item_completed.send(sender=Instance, item=instance,
                        member=instance.completed_by or instance.task.owner,
                        completion=instance)


__all__ = [
    "APPROVAL", "TRACKED", "acknowledge", "approval_history", "approve",
    "can_complete", "complete", "doers", "effort_share_minutes",
    "record_changes", "reject", "skip", "snapshot", "tasks_for", "uncomplete",
]
