from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from nora_home.displays.bus import send_to_display
from nora_home.displays.models import Display

logger = logging.getLogger(__name__)


@shared_task(queue="platform", expires=40)
def rotate_wall_display():
    """Advance every rotating display one panel.

    Deliberately server-driven rather than a browser timer: it means the kiosk can
    pin a panel and have every screen agree, and it keeps two wall screens in sync
    if the house ever grows a second one. `expires` stops a backed-up queue from
    firing a burst of stale rotations at once.
    """
    advanced = 0
    for display in Display.objects.filter(is_active=True, rotation_enabled=True):
        if display.is_pinned:
            continue
        if display.in_night_mode():
            send_to_display(display.slug, {"type": "night"})
            continue
        if not display.is_online:
            continue
        if send_to_display(display.slug, {"type": "next"}):
            advanced += 1
    return {"advanced": advanced}


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
