"""
The telemetry and integration bridge into Todo's system board (§8, "System
tasks").

**One-directional by design.** The measurement stays in telemetry where it can
be charted, and only the "someone should look at this" part becomes a task —
which is what keeps the system board short and actionable rather than a log
people learn to ignore. Nothing here reads a task back into telemetry or
integrations; a completed system task does not clear a threshold or reset a
failure count.

Wired as signal receivers rather than an import from telemetry or
integrations — CLAUDE.md: "Never import another app's models... send a signal
from nora_home.core.signals" instead. Connected in TodoConfig.ready().
"""

from __future__ import annotations

import logging

from django.dispatch import receiver

from nora_home.core.signals import integration_failing, threshold_crossed
from nora_home.todo.models import Priority, Task, TaskSource, TaskState
from nora_home.todo.reminders import ensure_default_reminder
from nora_home.todo.scheduling import materialize

logger = logging.getLogger(__name__)


def _system_owner():
    """Every active adult is an assignee (below), so any one of them can pick
    a system task up — `owner` only has to be *a* real, active adult for
    OwnedModel's sake, not a single point of responsibility. Admin first, so a
    house with one falls back to whoever is actually there."""
    from nora_home.accounts.models import HouseMember

    return (HouseMember.objects.filter(is_active=True, role=HouseMember.Role.ADMIN).first()
            or HouseMember.objects.filter(is_active=True, role=HouseMember.Role.ADULT).first())


def create_system_task(*, origin_ref: str, title: str, description: str = "",
                       priority: int = Priority.P2) -> Task | None:
    """A system task, created once per `origin_ref` while one is still open.

    Reusing the open task instead of creating a second one is what stops a
    threshold that stays breached, or an integration that keeps failing, from
    filling the board with duplicates of the same problem — the same
    suppression `notify_house`'s `dedupe_key` gives a notification, applied to
    a task instead. Once it is completed or archived, the next occurrence
    starts a fresh one, because at that point it is a new instance of the
    problem, not a continuation of the old one.

    Returns `None` rather than raising when there is nobody to own it — a
    freshly provisioned house with no adult yet added must not 500 on its
    first threshold breach.
    """
    existing = (Task.objects.alive()
               .filter(source=TaskSource.SYSTEM, origin_ref=origin_ref,
                       state=TaskState.OPEN)
               .first())
    if existing is not None:
        return existing

    owner = _system_owner()
    if owner is None:
        logger.warning("No active adult to own a system task (%s): %s",
                       origin_ref, title)
        return None

    from django.utils import timezone

    from nora_home.accounts.models import HouseMember

    task = Task.objects.create(
        title=title, description=description, owner=owner, priority=priority,
        source=TaskSource.SYSTEM, origin_ref=origin_ref,
        due_on=timezone.localdate(),
    )
    task.assignees.set(HouseMember.objects.filter(
        is_active=True, role__in=[HouseMember.Role.ADULT, HouseMember.Role.ADMIN]))
    materialize(task)
    ensure_default_reminder(task)
    logger.info("System task created: %s (%s)", title, origin_ref)
    return task


@receiver(threshold_crossed)
def _telemetry_threshold_crossed(sender, series, value, threshold, direction, **kwargs):
    """§8.2: "a threshold breach... creates a system task." Fires once per
    reading that is off-threshold, same as the notification this mirrors —
    the state=OPEN check in create_system_task is what keeps a sensor stuck
    over its bound from generating a new task on every single reading."""
    create_system_task(
        origin_ref=f"telemetry:{series.key}:{threshold}",
        title=f"{series.label} is {threshold} "
              f"({value:.{series.precision}f}{series.unit})",
        description=f"{series.label} crossed its {threshold} threshold, "
                    f"{direction} the configured bound.",
        priority=Priority.P1 if threshold == "alert" else Priority.P2,
    )


@receiver(integration_failing)
def _integration_keeps_failing(sender, integration, consecutive_failures, message, **kwargs):
    """§8.2: "an integration failing repeatedly." `integration_failing` only
    fires once per continuous-failure episode (nora_home.integrations.tasks),
    so this does not need its own throttling on top."""
    create_system_task(
        origin_ref=f"integration:{integration.pk}",
        title=f"{integration.name} keeps failing",
        description=f"{consecutive_failures} runs in a row failed: {message[:300]}",
        priority=Priority.P2,
    )
