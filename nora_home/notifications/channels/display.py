"""Put an alert on the always-on 24" wall display."""

from __future__ import annotations

from django.conf import settings

from nora_home.displays.bus import send_to_display
from nora_home.notifications.channels import BaseChannel

# How long a banner holds the wall display before rotation resumes.
HOLD_SECONDS = {"info": 8, "nudge": 12, "warning": 20, "alert": 45, "critical": 0}


class DisplayChannel(BaseChannel):
    name = "display"

    def send(self, notification, delivery) -> dict:  # noqa: ARG002
        slug = settings.NORA_HOME_MAIN_DISPLAY_SLUG
        send_to_display(slug, {
            "type": "banner",
            "severity": notification.severity,
            "title": notification.title,
            "body": notification.body[:400],
            "app": notification.app_slug,
            "hold_seconds": HOLD_SECONDS.get(notification.severity, 10),
            "recipient": notification.recipient.name if notification.recipient else None,
        })
        return {"target": slug, "ref": ""}
