"""Platform housekeeping tasks."""

from __future__ import annotations

import logging

from celery import shared_task
from django.utils import timezone

from nora_home.core.health import collect_health
from nora_home.core.models import AuditEvent, SystemHealthSnapshot

logger = logging.getLogger(__name__)


@shared_task(queue="platform")
def record_health_snapshot():
    """Store vitals so the System panel can show a trend, not just a moment."""
    report = collect_health()
    services = {name: probe.get("status") for name, probe in report["services"].items()}

    snapshot = SystemHealthSnapshot.objects.create(
        disk_percent=report["services"].get("disk", {}).get("percent_used"),
        cpu_temp_c=report["services"].get("cpu_temperature", {}).get("celsius"),
        services=services,
        healthy=report["healthy"],
    )

    if not report["healthy"]:
        from nora_home.notifications.api import notify_house

        notify_house(
            title="Nora Home is degraded",
            body="Unhealthy: " + ", ".join(report["degraded"]),
            severity="alert",
            app_slug="core",
            channels=["slack", "display"],
        )
    return {"healthy": report["healthy"], "snapshot_id": snapshot.pk}


@shared_task(queue="platform")
def prune_old_records(days: int = 180):
    """Keep the Pi's SD card from filling with history nobody reads."""
    cutoff = timezone.now() - timezone.timedelta(days=days)
    audit_deleted, _ = AuditEvent.objects.filter(
        created_at__lt=cutoff,
        severity__in=[AuditEvent.Severity.DEBUG, AuditEvent.Severity.INFO],
    ).delete()
    health_deleted, _ = SystemHealthSnapshot.objects.filter(
        created_at__lt=timezone.now() - timezone.timedelta(days=30)
    ).delete()
    logger.info("Pruned %s audit rows and %s health snapshots", audit_deleted, health_deleted)
    return {"audit": audit_deleted, "health": health_deleted}
