"""
The display bus — how anything in the house pushes to a screen.

Messages travel over the Channels layer (Redis in production, in-memory in dev), so
a Celery task, a view, or the kiosk consumer can all reach the wall display without
knowing anything about websockets.

    from nora_home.displays.bus import send_to_display, broadcast

    send_to_display("wall", {"type": "show", "panel": "tracker.WallAgendaPanel"})
    broadcast({"type": "refresh"})

Every send is best-effort: if the channel layer is down, the house logs it and keeps
running. A screen that misses a message re-syncs on its next heartbeat.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

GROUP_PREFIX = "display."
ALL_DISPLAYS_GROUP = "display.all"


def group_for(slug: str) -> str:
    return f"{GROUP_PREFIX}{slug}"


def send_to_display(slug: str, payload: dict) -> bool:
    """Push one message to one display. Returns False if it could not be sent."""
    return _send(group_for(slug), payload)


def broadcast(payload: dict) -> bool:
    """Push to every connected display at once — used for 'refresh' after a deploy."""
    return _send(ALL_DISPLAYS_GROUP, payload)


def _send(group: str, payload: dict) -> bool:
    layer = get_channel_layer()
    if layer is None:
        logger.warning("No channel layer configured; dropping display message")
        return False
    try:
        async_to_sync(layer.group_send)(group, {"type": "display.message",
                                                "payload": payload})
        return True
    except Exception:
        logger.exception("Could not send %r to %s", payload.get("type"), group)
        return False


def show_panel(slug: str, panel_key: str, *, pin_seconds: int = 0,
               issued_by: str = "kiosk") -> bool:
    """Put a specific panel on a display, optionally pinning it there.

    Pinning is what makes the kiosk useful: tap a panel, the wall holds it while you
    look, and rotation resumes on its own afterwards so nobody has to remember.
    """
    from django.utils import timezone

    from nora_home.displays.models import Display, DisplayCommand

    display = Display.objects.filter(slug=slug, is_active=True).first()
    if display is None:
        logger.warning("No such display: %s", slug)
        return False

    display.current_panel = panel_key
    display.pinned_until = (
        timezone.now() + timezone.timedelta(seconds=pin_seconds) if pin_seconds else None
    )
    display.save(update_fields=["current_panel", "pinned_until", "updated_at"])

    DisplayCommand.objects.create(
        display=display, action="show", issued_by=issued_by,
        payload={"panel": panel_key, "pin_seconds": pin_seconds},
    )
    return send_to_display(slug, {"type": "show", "panel": panel_key,
                                  "pin_seconds": pin_seconds})
