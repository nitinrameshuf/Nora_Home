"""
One time-series store for the whole house.

Weight, sleep, HRV, room temperature, the robot's battery and CPU, a portfolio
value, litres of water — they are all "a named number, measured at a time,
optionally about a person". Apps that need charts, trends, or thresholds should
record here rather than inventing another table.

    from nora_home.telemetry.api import record_reading
    record_reading("body.weight", 74.2, member=request.user, app_slug="health")

Two tables on purpose: Series is the definition (unit, thresholds, who owns it),
Reading is the data. That keeps the hot table narrow, which matters on a Pi.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from nora_home.core.models import TimeStampedModel


class Series(TimeStampedModel):
    """A named measurement. Keys are dotted and namespaced: `nora.battery`,
    `body.weight`, `house.living_room.temp`, `money.portfolio`."""

    class Direction(models.TextChoices):
        HIGHER_BETTER = "up", "Higher is better"
        LOWER_BETTER = "down", "Lower is better"
        RANGE = "range", "Stay inside a range"
        NEUTRAL = "neutral", "Just tracking"

    key = models.CharField(max_length=120, unique=True)
    label = models.CharField(max_length=120)
    description = models.CharField(max_length=255, blank=True)
    unit = models.CharField(max_length=24, blank=True, help_text="kg, °C, %, ms, USD…")
    app_slug = models.CharField(max_length=60, db_index=True, default="telemetry")
    category = models.CharField(
        max_length=40, blank=True, db_index=True,
        help_text="Cross-app grouping, e.g. 'health', 'house', 'robot' — lets the "
                  "home screen group series by theme instead of by which app owns "
                  "them. Optional; ungrouped series just sort under app_slug.")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.CASCADE, related_name="series",
                               help_text="Null for house-wide series.")

    direction = models.CharField(max_length=8, choices=Direction.choices,
                                 default=Direction.NEUTRAL)
    warn_below = models.FloatField(null=True, blank=True)
    warn_above = models.FloatField(null=True, blank=True)
    alert_below = models.FloatField(null=True, blank=True)
    alert_above = models.FloatField(null=True, blank=True)

    precision = models.PositiveSmallIntegerField(default=2)
    show_on_wall = models.BooleanField(default=False)
    retention_days = models.PositiveIntegerField(
        default=730, help_text="Raw readings older than this are rolled up and dropped.")
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name_plural = "series"
        ordering = ["app_slug", "key"]

    def __str__(self):
        return f"{self.label} ({self.key})"

    def latest(self):
        return self.readings.order_by("-recorded_at").first()

    def latest_value(self):
        reading = self.latest()
        return reading.value if reading else None

    def classify(self, value: float) -> str:
        """ok | warning | alert — used for colouring and for firing thresholds."""
        if self.alert_below is not None and value < self.alert_below:
            return "alert"
        if self.alert_above is not None and value > self.alert_above:
            return "alert"
        if self.warn_below is not None and value < self.warn_below:
            return "warning"
        if self.warn_above is not None and value > self.warn_above:
            return "warning"
        return "ok"


class Reading(models.Model):
    """One data point. No TimeStampedModel here — this table gets large, and
    `recorded_at` is the only time that matters."""

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="readings")
    value = models.FloatField()
    recorded_at = models.DateTimeField(default=timezone.now, db_index=True)
    member = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="readings")
    source = models.CharField(max_length=40, blank=True,
                              help_text="manual | robot | integration | derived")
    tags = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-recorded_at"]
        indexes = [models.Index(fields=["series", "-recorded_at"])]

    def __str__(self):
        return f"{self.series_id}={self.value} @ {self.recorded_at:%Y-%m-%d %H:%M}"


class HourlyRollup(models.Model):
    """Aggregates so a year-long chart does not read a million rows on a Pi."""

    series = models.ForeignKey(Series, on_delete=models.CASCADE, related_name="rollups")
    hour = models.DateTimeField(db_index=True)
    count = models.PositiveIntegerField(default=0)
    mean = models.FloatField()
    minimum = models.FloatField()
    maximum = models.FloatField()

    class Meta:
        ordering = ["-hour"]
        unique_together = [("series", "hour")]

    def __str__(self):
        return f"{self.series_id} {self.hour:%Y-%m-%d %H}h avg={self.mean:.2f}"
