"""In-app delivery: the bell menu, plus a live websocket push to open browsers."""

from __future__ import annotations

from nora_home.notifications.channels import BaseChannel


class InAppChannel(BaseChannel):
    name = "inapp"

    def send(self, notification, delivery) -> dict:  # noqa: ARG002
        # The Notification row *is* the in-app delivery; all this does is wake up
        # any browser currently showing the site so Nora can react immediately.
        from nora_home.ui.bot import push_notification

        push_notification(notification)
        target = notification.recipient.get_username() if notification.recipient else "house"
        return {"target": target, "ref": ""}
