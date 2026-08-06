from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.management import call_command
from django.utils import timezone

from nora_home.core.audit import record

logger = logging.getLogger(__name__)


@shared_task(queue="platform", time_limit=60 * 50)
def nightly_backup():
    """Runs at 03:30 by the beat schedule. Tells the house if it ever fails —
    a backup nobody notices breaking is not a backup."""
    started = timezone.now()
    try:
        call_command(
            "nora_backup",
            compress=True,
            to_object_storage=settings.NORA_HOME_BACKUP_TO_OBJECT_STORAGE,
        )
    except Exception as exc:
        logger.exception("Nightly backup failed")
        from nora_home.notifications.api import notify_house

        # Audited as well as notified: the notification is how someone finds out
        # tonight, the audit row is how they answer "when did backups actually
        # stop working" three weeks later, once the Slack message has scrolled
        # away. Both halves matter, and only one of them is durable.
        record("data", "backup.failed", subject="Nightly backup",
               severity="alert", source="celery", error=str(exc)[:300])
        notify_house(
            title="Backup failed",
            body=f"Last night's Nora Home backup did not complete: {exc}",
            severity="alert", app_slug="data", channels=["slack", "inapp"],
        )
        return {"ok": False, "error": str(exc)[:300]}

    record("data", "backup.completed", subject="Nightly backup", source="celery",
           seconds=round((timezone.now() - started).total_seconds(), 1))
    return {"ok": True}
