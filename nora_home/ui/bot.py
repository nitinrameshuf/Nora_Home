"""
The home bot — the little face that zips around the screen.

It is Nora Home's own avatar. **It is not Nora the robot**, which is a separate
machine with its own project; nothing in this module talks to the robot, and the
two should never be conflated in code or in copy.

Server-side this is just a message bus. `say()` pushes a line and a mood to whoever
is looking; the browser decides how it moves. House apps use this to make the system
feel alive rather than to convey anything important — anything that must be seen goes
through `nora_home.notifications`, which has delivery receipts.

    from nora_home.ui import bot
    bot.say("Three days on the trot. That's a streak.", mood="proud")

Moods the front end knows: idle, happy, proud, curious, thinking, concerned,
sleepy, celebrate. An unknown mood falls back to happy rather than breaking.
"""

from __future__ import annotations

import logging

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

logger = logging.getLogger(__name__)

BOT_GROUP = "nora_home.bot"

# Channels turns a dotted message type into an underscored consumer method, so this
# must stay in step with HomeBotConsumer.homebot_message.
BOT_MESSAGE_TYPE = "homebot.message"

MOODS = {"idle", "happy", "proud", "curious", "thinking", "concerned", "sleepy",
         "celebrate"}


def _push(payload: dict) -> bool:
    layer = get_channel_layer()
    if layer is None:
        return False
    try:
        async_to_sync(layer.group_send)(BOT_GROUP, {"type": BOT_MESSAGE_TYPE,
                                                    "payload": payload})
        return True
    except Exception:
        logger.exception("Could not push a home bot message")
        return False


def say(message: str, *, mood: str = "happy", surface: str = "all",
        duration_ms: int = 6000) -> bool:
    """Make the bot speak. `surface` is 'all' or one of phone/tablet/desktop/kiosk."""
    if mood not in MOODS:
        logger.debug("Unknown home bot mood %r; using happy", mood)
        mood = "happy"
    return _push({
        "type": "say",
        "message": message[:280],
        "mood": mood,
        "surface": surface,
        "duration_ms": duration_ms,
    })


def react(mood: str = "happy", *, surface: str = "all") -> bool:
    """A wordless reaction — a spin, a bounce, a shrug."""
    return _push({"type": "react", "mood": mood if mood in MOODS else "happy",
                  "surface": surface})


def push_notification(notification) -> bool:
    """Wake open browsers when a notification lands, so the bell updates live and
    the bot can glance toward it."""
    return _push({
        "type": "notification",
        "id": notification.pk,
        "title": notification.title,
        "body": notification.body[:200],
        "severity": notification.severity,
        "url": notification.url,
        "recipient": (notification.recipient.get_username()
                      if notification.recipient else None),
    })
