from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from nora_home.tracker.escalation import close_expired_windows, escalate_due_occurrences
from nora_home.tracker.models import Occurrence, Trackable
from nora_home.tracker.scheduling import materialize

logger = logging.getLogger(__name__)


@shared_task(queue="alerts")
def run_escalations():
    """The heartbeat that makes unfinished work impossible to ignore."""
    escalated = escalate_due_occurrences()
    expired = close_expired_windows()
    return {**escalated, **expired}


@shared_task(queue="platform")
def sweep_due_items():
    """Gentle first-touch reminder as things come due, before escalation bites."""
    from nora_home.notifications.api import notify

    now = timezone.now()
    soon = now + timezone.timedelta(minutes=30)
    upcoming = (Occurrence.objects
                .open()
                .filter(due_at__gte=now, due_at__lte=soon, escalation_level=0)
                .select_related("trackable", "trackable__owner"))

    nudged = 0
    for occurrence in upcoming:
        notify(
            occurrence.trackable.owner,
            title=f"Coming up: {occurrence.trackable.title}",
            body=f"Due at {timezone.localtime(occurrence.due_at):%H:%M}.",
            severity="info", app_slug=occurrence.trackable.app_slug,
            url=occurrence.trackable.url or "/tracker/",
            dedupe_key=f"soon:{occurrence.uuid}", dedupe_minutes=120,
        )
        nudged += 1
    return {"nudged": nudged}


@shared_task(queue="platform")
def materialize_schedules():
    """Keep the two-week horizon of occurrences filled in."""
    created = 0
    for trackable in Trackable.objects.filter(is_active=True, deleted_at__isnull=True):
        try:
            created += materialize(trackable)
        except Exception:
            logger.exception("Could not materialize trackable %s", trackable.pk)
    if created:
        logger.info("Materialized %s new occurrences", created)
    return {"created": created}
