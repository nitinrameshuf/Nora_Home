"""
Recording measurements. This is the whole interface house apps need.

    from nora_home.telemetry.api import record_reading, define_series

    define_series("nora_home.battery", "Nora battery", unit="%", app_slug="robot",
                  alert_below=15, direction="up", show_on_wall=True)

    record_reading("nora_home.battery", 82.0, source="robot")

`record_reading` creates the series on first use, so a quick experiment does not
need a migration — but define it explicitly once you know the thresholds, because
that is what turns a number into an alert.
"""

from __future__ import annotations

import logging

from django.utils import timezone

from nora_home.core.signals import threshold_crossed
from nora_home.telemetry.models import Reading, Series

logger = logging.getLogger(__name__)


def define_series(key: str, label: str, *, unit: str = "", app_slug: str = "telemetry",
                  member=None, direction: str = "neutral", description: str = "",
                  warn_below=None, warn_above=None, alert_below=None, alert_above=None,
                  show_on_wall: bool = False, precision: int = 2,
                  retention_days: int = 730) -> Series:
    series, _ = Series.objects.update_or_create(
        key=key,
        defaults={
            "label": label, "unit": unit, "app_slug": app_slug, "member": member,
            "direction": direction, "description": description,
            "warn_below": warn_below, "warn_above": warn_above,
            "alert_below": alert_below, "alert_above": alert_above,
            "show_on_wall": show_on_wall, "precision": precision,
            "retention_days": retention_days, "is_active": True,
        },
    )
    return series


def record_reading(key: str, value: float, *, member=None, source: str = "manual",
                   recorded_at=None, app_slug: str = "telemetry", **tags) -> Reading:
    """Store one measurement and fire a threshold signal if it crosses a bound."""
    series, created = Series.objects.get_or_create(
        key=key,
        defaults={"label": key.replace(".", " ").title(), "app_slug": app_slug,
                  "member": member},
    )
    if created:
        logger.info("Auto-created telemetry series %s for %s", key, app_slug)

    reading = Reading.objects.create(
        series=series, value=float(value), member=member, source=source,
        recorded_at=recorded_at or timezone.now(), tags=tags,
    )

    status = series.classify(reading.value)
    if status != "ok":
        _raise_threshold(series, reading, status)
    return reading


def _raise_threshold(series: Series, reading: Reading, status: str):
    from nora_home.notifications.api import notify, notify_house

    direction = "below" if (
        (series.alert_below is not None and reading.value < series.alert_below)
        or (series.warn_below is not None and reading.value < series.warn_below)
    ) else "above"

    threshold_crossed.send(sender=Series, series=series, value=reading.value,
                           threshold=status, direction=direction)

    title = f"{series.label}: {reading.value:.{series.precision}f}{series.unit}"
    body = f"That is {direction} the {status} threshold for {series.label}."
    severity = "alert" if status == "alert" else "warning"
    dedupe = f"threshold:{series.key}:{status}"

    if series.member:
        notify(series.member, title=title, body=body, severity=severity,
               app_slug=series.app_slug, dedupe_key=dedupe, dedupe_minutes=180)
    else:
        notify_house(title=title, body=body, severity=severity,
                     app_slug=series.app_slug, dedupe_key=dedupe)


def series_history(key: str, *, hours: int = 24, limit: int = 500):
    since = timezone.now() - timezone.timedelta(hours=hours)
    return (Reading.objects.filter(series__key=key, recorded_at__gte=since)
            .order_by("recorded_at")[:limit])
