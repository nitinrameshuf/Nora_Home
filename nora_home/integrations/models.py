"""Installed integrations and their run history."""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from nora_home.core.models import TimeStampedModel


class Integration(TimeStampedModel):
    """One configured connection to an outside service.

    Credentials are deliberately absent: `Integration.secret()` reads them from the
    environment, so a database dump shared for debugging carries no tokens.
    """

    slug = models.SlugField(help_text="Matches the registered Integration class.")
    name = models.CharField(max_length=80)
    config = models.JSONField(default=dict, blank=True)

    interval_minutes = models.PositiveIntegerField(default=15)
    is_enabled = models.BooleanField(default=True, db_index=True)

    last_run_at = models.DateTimeField(null=True, blank=True, db_index=True)
    last_success_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveSmallIntegerField(default=0)
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]
        unique_together = [("slug", "name")]

    def __str__(self):
        return self.name

    @property
    def is_due(self) -> bool:
        if not self.is_enabled:
            return False
        if self.last_run_at is None:
            return True
        # Back off exponentially while failing, so a dead service is polled
        # every few hours rather than every few minutes.
        backoff = min(2 ** self.consecutive_failures, 16)
        interval = self.interval_minutes * (backoff if self.consecutive_failures else 1)
        return timezone.now() >= self.last_run_at + timezone.timedelta(minutes=interval)

    @property
    def is_healthy(self) -> bool:
        return self.consecutive_failures == 0


class IntegrationRun(TimeStampedModel):
    integration = models.ForeignKey(Integration, on_delete=models.CASCADE,
                                    related_name="runs")
    succeeded = models.BooleanField(default=False, db_index=True)
    duration_ms = models.PositiveIntegerField(default=0)
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.integration_id} {'ok' if self.succeeded else 'failed'}"
