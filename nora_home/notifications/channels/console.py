"""Development channel — prints instead of sending. Never enable on the Pi."""

from __future__ import annotations

import logging

from nora_home.notifications.channels import BaseChannel

logger = logging.getLogger(__name__)


class ConsoleChannel(BaseChannel):
    name = "console"

    def send(self, notification, delivery) -> dict:  # noqa: ARG002
        who = notification.recipient.name if notification.recipient else "the house"
        logger.info("NOTIFY[%s] → %s: %s | %s",
                    notification.severity, who, notification.title, notification.body)
        return {"target": "console", "ref": ""}
