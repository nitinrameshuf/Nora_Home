"""
Reacting to the platform without coupling to it.

The tracker fires `item_completed` for every app. Filtering on `app_slug` here is
how a house app hears about its own work without importing anyone else's models.
"""

from __future__ import annotations

import logging

from django.dispatch import receiver

from nora_home.core.signals import item_completed
from nora_home.ui import bot

logger = logging.getLogger(__name__)

CELEBRATE_AT = {7, 14, 30, 60, 100, 365}


@receiver(item_completed)
def celebrate_streaks(sender, item, member, completion, **kwargs):  # noqa: ARG001
    """Say something when a streak hits a round number — but only then. A bot that
    congratulates every single tick stops meaning anything."""
    if item.trackable.app_slug != "habits":
        return

    streak = item.trackable.current_streak()
    if streak not in CELEBRATE_AT:
        return

    bot.say(f"{streak} days of {item.trackable.title}. That's real now.",
            mood="proud")

    from nora_home.notifications.api import notify

    notify(member,
           title=f"{streak}-day streak: {item.trackable.title}",
           body="Worth noticing.",
           severity="info", app_slug="habits", icon="repeat",
           dedupe_key=f"streak:{item.trackable.uuid}:{streak}")
