from __future__ import annotations

import logging

from celery import shared_task
from django.conf import settings
from django.core.management import call_command

logger = logging.getLogger(__name__)


@shared_task(queue="platform", time_limit=60 * 50)
def nightly_backup():
    """Runs at 03:30 by the beat schedule. Tells the house if it ever fails —
    a backup nobody notices breaking is not a backup."""
    try:
        call_command(
            "nora_backup",
            compress=True,
            to_object_storage=settings.NORA_HOME_BACKUP_TO_OBJECT_STORAGE,
        )
    except Exception as exc:
        logger.exception("Nightly backup failed")
        from nora_home.notifications.api import notify_house

        notify_house(
            title="Backup failed",
            body=f"Last night's Nora Home backup did not complete: {exc}",
            severity="alert", app_slug="data", channels=["slack", "inapp"],
        )
        return {"ok": False, "error": str(exc)[:300]}
    return {"ok": True}
