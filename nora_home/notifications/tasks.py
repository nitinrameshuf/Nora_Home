"""Delivery workers. Failures retry with backoff; permanent ones are recorded."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from nora_home.notifications.channels import ChannelError, get_channel
from nora_home.notifications.models import Delivery, Notification

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4


@shared_task(queue="alerts")
def deliver_notification(notification_id: int):
    """Push one notification down every channel queued for it."""
    try:
        notification = Notification.objects.select_related("recipient").get(
            pk=notification_id)
    except Notification.DoesNotExist:
        logger.warning("Notification %s vanished before delivery", notification_id)
        return {"delivered": 0}

    delivered = 0
    for delivery in notification.deliveries.filter(status=Delivery.Status.PENDING):
        if _attempt(notification, delivery):
            delivered += 1
    return {"notification": notification_id, "delivered": delivered}


def _attempt(notification: Notification, delivery: Delivery) -> bool:
    channel = get_channel(delivery.channel)
    if channel is None:
        delivery.status = Delivery.Status.SKIPPED
        delivery.error = f"Channel {delivery.channel} is not registered."
        delivery.save(update_fields=["status", "error", "updated_at"])
        return False

    if not channel.is_configured():
        delivery.status = Delivery.Status.SKIPPED
        delivery.error = f"Channel {delivery.channel} is not configured."
        delivery.save(update_fields=["status", "error", "updated_at"])
        logger.info("Skipped %s delivery: not configured", delivery.channel)
        return False

    delivery.attempts += 1
    try:
        result = channel.send(notification, delivery)
    except ChannelError as exc:
        delivery.status = (Delivery.Status.FAILED if delivery.attempts >= MAX_ATTEMPTS
                           else Delivery.Status.PENDING)
        delivery.error = str(exc)[:1000]
        delivery.save(update_fields=["status", "attempts", "error", "updated_at"])
        logger.warning("Delivery %s via %s failed (attempt %s): %s",
                       delivery.pk, delivery.channel, delivery.attempts, exc)
        return False
    except Exception as exc:
        delivery.status = Delivery.Status.FAILED
        delivery.error = f"{type(exc).__name__}: {exc}"[:1000]
        delivery.save(update_fields=["status", "attempts", "error", "updated_at"])
        logger.exception("Delivery %s via %s raised", delivery.pk, delivery.channel)
        return False

    delivery.status = Delivery.Status.SENT
    delivery.sent_at = timezone.now()
    delivery.target = str(result.get("target", ""))[:120]
    delivery.provider_ref = str(result.get("ref", ""))[:120]
    delivery.error = ""
    delivery.save(update_fields=["status", "attempts", "sent_at", "target",
                                 "provider_ref", "error", "updated_at"])
    return True


@shared_task(queue="alerts")
def retry_failed_deliveries():
    """Sweep pending deliveries that a transient outage left behind."""
    cutoff = timezone.now() - timezone.timedelta(hours=6)
    stuck = (Delivery.objects
             .filter(status=Delivery.Status.PENDING, created_at__gte=cutoff,
                     attempts__lt=MAX_ATTEMPTS)
             .select_related("notification", "notification__recipient"))
    retried = sum(1 for d in stuck if _attempt(d.notification, d))
    if retried:
        logger.info("Retried %s stuck deliveries", retried)
    return {"retried": retried}
