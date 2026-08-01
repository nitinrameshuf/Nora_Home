"""
Scheduled work.

Any `tasks.py` in an installed app is autodiscovered by Celery. To run one on a
schedule, add a PeriodicTask row in the admin (Django Celery Beat → Periodic tasks)
rather than editing config/celery.py — that keeps the platform's schedule and the
family's schedules separate, and lets someone retime it without a deploy.
"""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from nora_home.telemetry.api import record_reading
from nora_home.tracker.models import Occurrence

logger = logging.getLogger(__name__)


@shared_task(queue="apps")
def record_weekly_completion_rate():
    """Turn last week's habit history into a number the house can chart.

    Recording into telemetry rather than a private table means the wall display,
    the MCP tools, and the AI all see it without this app doing anything else.
    """
    from nora_home.accounts.models import HouseMember

    since = timezone.now() - timezone.timedelta(days=7)
    recorded = 0

    for member in HouseMember.objects.filter(is_active=True):
        window = Occurrence.objects.filter(
            trackable__app_slug="habits", trackable__owner=member, due_at__gte=since)
        done = window.filter(status=Occurrence.Status.DONE).count()
        total = done + window.filter(status=Occurrence.Status.MISSED).count()
        if not total:
            continue

        record_reading("habits.completion_rate", round(done / total * 100, 1),
                       member=member, source="derived", app_slug="habits")
        recorded += 1

    return {"members": recorded}
