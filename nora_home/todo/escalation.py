"""
Todo's escalation ladder — carried over from the tracker "largely intact"
(docs/Main_App/subsystems/todo.md §9): same `EscalationPolicy` model, same
rung shape (`after_minutes` / `notify` / `severity` / `channels`), same
audiences (`owner` / `chain` / `adults` / `house`). What changes is what it
walks (`Instance` instead of `Occurrence`) and where it writes its trail
(`ChangeEvent`, Todo's own history table, instead of a second `EscalationEvent`
model — Todo already has one append-only history table for everything else
that happens to a task, and an escalation firing is exactly that kind of
event).

**Opt-in, off by default** — `Task.escalation_enabled`. Escalating "Join AI &
Robotic Communities" would be noise nobody asked for. **Archived tasks never
escalate** — filtered at the query, not just documented.

The audience is always the task's `owner` alone, never its assignees. A shared
task still has exactly one person escalation chases — that is what keeps the
chain-of-contacts ladder meaningful; see `nora_home.todo.api.doers()` for the
one place that *does* fan out to every assignee (reminders).
"""

from __future__ import annotations

import logging

from django.utils import timezone

from nora_home.core.audit import record
from nora_home.core.signals import escalation_raised
from nora_home.notifications.api import notify, notify_house
from nora_home.todo.models import (
    ChangeEvent,
    EscalationPolicy,
    Instance,
    InstanceOutcome,
    TaskState,
)

logger = logging.getLogger(__name__)

ESCALATION = "escalation"


def escalate_due_instances(limit: int = 200) -> dict:
    """Advance the ladder for everything currently overdue. Safe to run every
    few minutes; each rung fires at most once, thanks to `escalation_level`."""
    now = timezone.now()
    candidates = (
        Instance.objects
        .filter(outcome=InstanceOutcome.PENDING, due_at__lt=now,
                acknowledged_at__isnull=True,
                task__escalation_enabled=True, task__state=TaskState.OPEN,
                task__deleted_at__isnull=True)
        .select_related("task", "task__owner", "task__escalation_policy")
        .order_by("due_at")[:limit]
    )

    raised = 0
    for instance in candidates:
        try:
            if _advance(instance, now):
                raised += 1
        except Exception:
            logger.exception("Escalation failed for instance %s", instance.pk)

    return {"checked": len(candidates), "raised": raised}


def _advance(instance: Instance, now) -> bool:
    task = instance.task
    policy = task.escalation_policy or EscalationPolicy.get_default()
    levels = policy.levels or []
    if instance.escalation_level >= len(levels):
        return False

    overdue_minutes = (now - instance.due_at).total_seconds() / 60 - policy.grace_minutes
    rung = levels[instance.escalation_level]
    if overdue_minutes < float(rung.get("after_minutes", 0)):
        return False

    audience = rung.get("notify", "owner")
    severity = rung.get("severity", "warning")
    channels = rung.get("channels")
    level = instance.escalation_level + 1

    recipients = _resolve_audience(task, audience, level)
    _send(instance, recipients, audience, severity, channels, level)

    ChangeEvent.objects.create(
        task=task, instance=instance, field=ESCALATION,
        from_value=instance.escalation_level, to_value=level,
        reason=f"{audience}: notified {len(recipients)}",
    )

    instance.escalation_level = level
    instance.last_escalated_at = now
    instance.save(update_fields=["escalation_level", "last_escalated_at", "updated_at"])

    escalation_raised.send(sender=Instance, item=instance, level=level, notified=recipients)
    record("todo", "escalation.raised", subject=task.title,
          severity="alert" if level >= 3 else "warning",
          source="celery", level=level, audience=audience, instance=str(instance.uuid))
    logger.info("Escalated '%s' to level %s (%s)", task.title, level, audience)
    return True


def _resolve_audience(task, audience: str, level: int) -> list:
    from nora_home.accounts.models import HouseMember

    owner = task.owner
    if audience == "owner":
        return [owner]
    if audience == "chain":
        chain = owner.escalation_chain()
        # Level 3 uses chain rung 1, level 4 uses rung 2, and so on — the
        # offset exists because the first two rungs are "owner" by convention
        # on all three seeded policies.
        index = max(0, level - 3)
        return chain[index:index + 1] or chain[:1]
    if audience == "adults":
        return list(HouseMember.objects.filter(
            is_active=True, role__in=[HouseMember.Role.ADULT, HouseMember.Role.ADMIN]))
    if audience == "house":
        return list(HouseMember.objects.filter(is_active=True))
    logger.warning("Unknown escalation audience %r; defaulting to owner", audience)
    return [owner]


def _send(instance: Instance, recipients, audience: str, severity: str, channels, level: int):
    task = instance.task
    minutes_overdue = max(0, int((timezone.now() - instance.due_at).total_seconds() // 60))
    hours = minutes_overdue // 60
    lateness = f"{hours}h late" if hours else f"{minutes_overdue}m late"
    url = f"/todo/t/{task.uuid}/"

    if audience == "house":
        notify_house(
            title=f"Still not done: {task.title}",
            body=f"{task.owner.name} was due to do this {lateness}. Level {level} escalation.",
            severity=severity, app_slug="todo", url=url,
            dedupe_key=f"todo-esc:{instance.uuid}:{level}", channels=channels,
        )
        return

    for member in recipients:
        is_owner = member == task.owner
        if is_owner:
            title = f"Overdue: {task.title}"
            body = f"This was due {lateness}."
        else:
            title = f"{task.owner.name} hasn't done: {task.title}"
            body = (f"Due {timezone.localtime(instance.due_at):%a %d %b %H:%M} — {lateness}. "
                    f"You're on the escalation list for {task.owner.name}.")
        notify(member, title=title, body=body, severity=severity,
              app_slug="todo", url=url,
              dedupe_key=f"todo-esc:{instance.uuid}:{level}:{member.pk}",
              channels=channels, instance=str(instance.uuid), level=level)
