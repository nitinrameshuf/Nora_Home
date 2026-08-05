"""
The display bus — how anything in the house pushes to a screen.

Messages travel over the Channels layer (Redis in production, in-memory in dev), so
a Celery task, a view, or the kiosk consumer can all reach the wall display without
knowing anything about websockets.

    from nora_home.displays.bus import send_to_display, broadcast

    send_to_display("wall", {"type": "navigate", "path": "/home/"})
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
