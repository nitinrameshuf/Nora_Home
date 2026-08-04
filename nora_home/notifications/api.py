"""
The notification API house apps should use. This is the whole surface:

    from nora_home.notifications.api import notify, notify_house

    notify(member, title="Water the plants", body="It's been four days.",
           severity="nudge", app_slug="plants", url="/app/plants/")

    notify_house(title="Power outage", body="UPS on battery.",
                 severity="critical", app_slug="house")

Delivery is asynchronous by default (queued to Celery). Pass `sync=True` when you
are already inside a task and want the receipt before returning.
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.utils import timezone

from nora_home.notifications.models import QUIET_HOURS_OVERRIDE, Delivery, Notification, Severity

logger = logging.getLogger(__name__)

DEDUPE_WINDOW_MINUTES = 60


def notify(recipient, *, title: str, body: str = "", app_slug: str = "",
           severity: str = Severity.INFO, url: str = "", icon: str = "",
           channels: list[str] | None = None, dedupe_key: str = "",
           dedupe_minutes: int = DEDUPE_WINDOW_MINUTES, sync: bool = False,
           **context) -> Notification | None:
    """Tell one person something. Returns None if deduplicated away."""
    if dedupe_key and _recently_sent(dedupe_key, recipient, dedupe_minutes):
        logger.debug("Suppressed duplicate notification %s", dedupe_key)
        return None

    notification = Notification.objects.create(
        app_slug=app_slug or "core",
        title=title[:160],
        body=body,
        severity=severity,
        recipient=recipient,
        url=url,
        icon=icon,
        dedupe_key=dedupe_key,
        context=context,
    )

    for channel in _resolve_channels(recipient, severity, channels):
        Delivery.objects.create(notification=notification, channel=channel)

    _dispatch(notification.pk, sync=sync)
    return notification


def notify_house(*, title: str, body: str = "", app_slug: str = "",
                 severity: str = Severity.INFO, url: str = "", icon: str = "",
                 channels: list[str] | None = None, dedupe_key: str = "",
                 dedupe_minutes: int = DEDUPE_WINDOW_MINUTES,
                 sync: bool = False, **context) -> Notification | None:
    """Tell everyone. Goes to the house Slack channel and the wall display.

    Returns None if deduplicated away, same as notify(). House-wide alerts need
    this at least as much as personal ones do: every caller that passes a
    dedupe_key here is a repeating source — a threshold on a stuck sensor, an
    integration that keeps failing, a top-rung escalation — and without
    suppression each one puts a fresh banner on the wall on every single cycle.
    """
    if dedupe_key and _recently_sent(dedupe_key, None, dedupe_minutes):
        logger.debug("Suppressed duplicate house notification %s", dedupe_key)
        return None

    notification = Notification.objects.create(
        app_slug=app_slug or "core", title=title[:160], body=body, severity=severity,
        recipient=None, url=url, icon=icon, dedupe_key=dedupe_key, context=context,
    )
    for channel in channels or ["slack", "display", "inapp"]:
        Delivery.objects.create(notification=notification, channel=channel)
    _dispatch(notification.pk, sync=sync)
    return notification


def _resolve_channels(recipient, severity: str, override: list[str] | None) -> list[str]:
    if override:
        return [c for c in override if c in settings.NORA_HOME_NOTIFICATION_CHANNELS]

    if recipient is None:
        return list(settings.NORA_HOME_NOTIFICATION_DEFAULT_CHANNELS)

    if not recipient.notifications_enabled:
        return ["inapp"]  # still recorded, just never pushed

    preferred = recipient.preferred_channels or settings.NORA_HOME_NOTIFICATION_DEFAULT_CHANNELS
    chosen = [c for c in preferred if c in settings.NORA_HOME_NOTIFICATION_CHANNELS]

    # Quiet hours drop push channels unless it genuinely cannot wait.
    if recipient.in_quiet_hours() and severity not in QUIET_HOURS_OVERRIDE:
        chosen = [c for c in chosen if c == "inapp"] or ["inapp"]

    return chosen or ["inapp"]


def _recently_sent(dedupe_key: str, recipient, minutes: int) -> bool:
    cutoff = timezone.now() - timezone.timedelta(minutes=minutes)
    return Notification.objects.filter(
        dedupe_key=dedupe_key, recipient=recipient, created_at__gte=cutoff
    ).exists()


def _dispatch(notification_id: int, *, sync: bool):
    from nora_home.notifications.tasks import deliver_notification

    if sync or getattr(settings, "CELERY_TASK_ALWAYS_EAGER", False):
        deliver_notification(notification_id)
    else:
        deliver_notification.apply_async(args=[notification_id], queue="alerts")
