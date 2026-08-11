from __future__ import annotations

import logging
import os

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


# key -> (probe, kwargs for define_series). Defined once at import time so
# collect_vitals() and anything inspecting the schedule see the same list.
_VITAL_SERIES = [
    ("pi.cpu_percent", "CPU", "%", "down", {"warn_above": 85, "alert_above": 95}),
    ("pi.memory_percent", "Memory", "%", "down", {"warn_above": 85, "alert_above": 95}),
    ("pi.load_average", "Load average", "", "down",
     {"warn_above": max(2, os.cpu_count() or 4),
      "alert_above": 2 * (os.cpu_count() or 4)}),
    ("pi.uptime_hours", "Uptime", "h", "neutral", {}),
    ("pi.fan_rpm", "Fan speed", "rpm", "neutral", {}),
    # Any bit set means something worth knowing happened; classify() alerts
    # on value > alert_above, so 0 (nothing set) is the only "ok" value.
    ("pi.throttled", "Throttled flags", "", "down", {"alert_above": 0}),
]


@shared_task(queue="platform")
def collect_vitals():
    """CPU, memory, load, uptime, fan and throttling — the rest of the Pi's
    vitals, alongside the temperature and disk core.health already collects.
    Never raises: one missing probe (no fan on a dev box) just records fewer
    series, same discipline as nora_home.core.vitals.rail_vitals()."""
    from nora_home.telemetry import probes
    from nora_home.telemetry.api import define_series, record_reading

    readers = {
        "pi.cpu_percent": probes.read_cpu_percent,
        "pi.memory_percent": probes.read_memory_percent,
        "pi.load_average": probes.read_load_average,
        "pi.uptime_hours": probes.read_uptime_hours,
        "pi.fan_rpm": probes.read_fan_rpm,
        "pi.throttled": probes.read_throttled,
    }

    recorded = []
    for key, label, unit, direction, thresholds in _VITAL_SERIES:
        try:
            value = readers[key]()
            if value is None:
                continue
            define_series(key, label, unit=unit, app_slug="telemetry",
                          category="house", direction=direction,
                          show_on_wall=False, **thresholds)
            record_reading(key, value, source="probe", app_slug="telemetry")
            recorded.append(key)
        except Exception:
            logger.exception("Vitals probe %s failed", key)
    return {"recorded": recorded}


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
