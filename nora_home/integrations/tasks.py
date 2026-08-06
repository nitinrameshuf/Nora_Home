from __future__ import annotations

import logging
import time

from celery import shared_task
from django.utils import timezone

from nora_home.core.signals import integration_failing, integration_synced
from nora_home.integrations.base import IntegrationError, get_class
from nora_home.integrations.models import Integration, IntegrationRun

logger = logging.getLogger(__name__)

# Alert the house after this many consecutive failures — once, not every cycle.
FAILURE_ALERT_THRESHOLD = 3


@shared_task(queue="integrations")
def poll_due_integrations():
    """Fan out one task per integration that is due, so a slow service cannot
    delay the others."""
    due = [i.pk for i in Integration.objects.filter(is_enabled=True) if i.is_due]
    for pk in due:
        run_integration.apply_async(args=[pk], queue="integrations")
    return {"dispatched": len(due)}


@shared_task(queue="integrations", time_limit=180)
def run_integration(integration_id: int):
    integration = Integration.objects.filter(pk=integration_id).first()
    if integration is None:
        return {"ok": False, "error": "integration no longer exists"}

    klass = get_class(integration.slug)
    if klass is None:
        logger.error("No registered integration class for %r", integration.slug)
        return {"ok": False, "error": f"unknown integration {integration.slug}"}

    started = time.monotonic()
    integration.last_run_at = timezone.now()

    try:
        summary = klass(integration).fetch() or {}
    except IntegrationError as exc:
        return _record_failure(integration, str(exc), started, expected=True)
    except Exception as exc:
        logger.exception("Integration %s raised", integration.slug)
        return _record_failure(integration, f"{type(exc).__name__}: {exc}", started,
                               expected=False)

    duration_ms = int((time.monotonic() - started) * 1000)
    IntegrationRun.objects.create(integration=integration, succeeded=True,
                                  duration_ms=duration_ms, summary=summary)

    integration.last_success_at = timezone.now()
    integration.consecutive_failures = 0
    integration.last_error = ""
    integration.save(update_fields=["last_run_at", "last_success_at",
                                    "consecutive_failures", "last_error", "updated_at"])

    integration_synced.send(sender=Integration, integration=integration,
                            records=summary, duration_ms=duration_ms)
    return {"ok": True, "summary": summary, "duration_ms": duration_ms}


def _record_failure(integration: Integration, message: str, started: float,
                    *, expected: bool):
    duration_ms = int((time.monotonic() - started) * 1000)
    IntegrationRun.objects.create(integration=integration, succeeded=False,
                                  duration_ms=duration_ms, error=message[:2000])

    integration.consecutive_failures += 1
    integration.last_error = message[:2000]
    integration.save(update_fields=["last_run_at", "consecutive_failures",
                                    "last_error", "updated_at"])

    if integration.consecutive_failures == FAILURE_ALERT_THRESHOLD:
        from nora_home.notifications.api import notify_house

        notify_house(
            title=f"{integration.name} keeps failing",
            body=f"{FAILURE_ALERT_THRESHOLD} runs in a row failed: {message[:300]}",
            severity="warning", app_slug="integrations",
            dedupe_key=f"integration-down:{integration.pk}",
        )
        integration_failing.send(sender=Integration, integration=integration,
                                 consecutive_failures=integration.consecutive_failures,
                                 message=message)

    logger.warning("Integration %s failed (%s): %s", integration.slug,
                   "expected" if expected else "unexpected", message[:200])
    return {"ok": False, "error": message[:300]}
