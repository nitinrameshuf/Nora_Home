from __future__ import annotations

import logging

from celery import shared_task
from django.db.models import Avg, Count, Max, Min
from django.db.models.functions import TruncHour
from django.utils import timezone

from nora_home.telemetry.models import HourlyRollup, Reading, Series

logger = logging.getLogger(__name__)


@shared_task(queue="platform")
def rollup_hourly(hours_back: int = 3):
    """Summarise recent readings into HourlyRollup rows.

    Runs a few hours behind the present so late-arriving readings (a robot that was
    offline, a phone that synced later) are still included in their own hour.
    """
    since = timezone.now() - timezone.timedelta(hours=hours_back)
    written = 0

    for series in Series.objects.filter(is_active=True):
        buckets = (Reading.objects
                   .filter(series=series, recorded_at__gte=since)
                   .annotate(hour=TruncHour("recorded_at"))
                   .values("hour")
                   .annotate(n=Count("id"), mean=Avg("value"),
                             lo=Min("value"), hi=Max("value")))
        for bucket in buckets:
            HourlyRollup.objects.update_or_create(
                series=series, hour=bucket["hour"],
                defaults={"count": bucket["n"], "mean": bucket["mean"],
                          "minimum": bucket["lo"], "maximum": bucket["hi"]},
            )
            written += 1
    return {"rollups": written}


@shared_task(queue="platform")
def prune_readings():
    """Drop raw readings past each series' retention window; rollups survive, so
    long-term trends stay visible without the row count."""
    total = 0
    for series in Series.objects.all():
        cutoff = timezone.now() - timezone.timedelta(days=series.retention_days)
        deleted, _ = Reading.objects.filter(series=series,
                                            recorded_at__lt=cutoff).delete()
        total += deleted
    if total:
        logger.info("Pruned %s raw telemetry readings", total)
    return {"deleted": total}
