from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from nora_home.displays.models import Display

logger = logging.getLogger(__name__)


# rotate_wall_display() lived here: every 45 seconds it sent "next" to advance
# the ambient wall's panel rotation. That wall was replaced by one that mirrors
# a real page of the app, chosen from the kiosk, and wall-live.js has no "next"
# case at all — so the task woke the worker on a timer forever to send a message
# nothing listened for. Removed along with its Celery beat entry.


@shared_task(queue="platform")
def check_displays_online():
    """Tell the house when the always-on display stops being on."""
    from nora_home.notifications.api import notify_house

    for display in Display.objects.filter(is_active=True, kind=Display.Kind.WALL):
        if display.is_online or display.last_seen_at is None:
            continue
        offline_minutes = int(
            (timezone.now() - display.last_seen_at).total_seconds() // 60)
        if offline_minutes < 10:
            continue
        notify_house(
            title=f"{display.name} is offline",
            body=f"No heartbeat for {offline_minutes} minutes. The kiosk browser may "
                 "have crashed, or the Pi lost that HDMI output.",
            severity="warning", app_slug="displays",
            dedupe_key=f"display-offline:{display.slug}",
        )
    return {"checked": True}
