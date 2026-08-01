"""
Notification channel backends.

A channel takes a Notification and a Delivery and gets it in front of a human.
Add one by subclassing BaseChannel and registering it in
settings.NORA_HOME_NOTIFICATION_CHANNELS.
"""

from __future__ import annotations

import logging
from importlib import import_module

from django.conf import settings

logger = logging.getLogger(__name__)


class ChannelError(Exception):
    """Raised by a channel when delivery failed but is worth retrying."""


class BaseChannel:
    name = "base"

    def send(self, notification, delivery) -> dict:
        """Deliver, or raise ChannelError. Return {"target": ..., "ref": ...}."""
        raise NotImplementedError

    def is_configured(self) -> bool:
        return True


def get_channel(name: str) -> BaseChannel | None:
    dotted = settings.NORA_HOME_NOTIFICATION_CHANNELS.get(name)
    if not dotted:
        logger.warning("Unknown notification channel %r", name)
        return None
    module_path, class_name = dotted.rsplit(".", 1)
    try:
        return getattr(import_module(module_path), class_name)()
    except Exception:
        logger.exception("Could not load notification channel %s", dotted)
        return None
