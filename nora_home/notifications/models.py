"""
Notifications and their delivery receipts.

A Notification is the *intent* ("tell Dad the filter is overdue"). A Delivery is one
attempt to get it onto one channel. Keeping them separate is what makes retries,
escalation proof, and "did anyone actually see this?" answerable.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from nora_home.core.models import TimeStampedModel


class Severity(models.TextChoices):
    INFO = "info", "Info"
    NUDGE = "nudge", "Nudge"
    WARNING = "warning", "Warning"
    ALERT = "alert", "Alert"
    CRITICAL = "critical", "Critical"


# Quiet hours are ignored at or above this severity.
QUIET_HOURS_OVERRIDE = {Severity.ALERT, Severity.CRITICAL}


class Notification(TimeStampedModel):
    app_slug = models.CharField(max_length=60, db_index=True)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    severity = models.CharField(max_length=10, choices=Severity.choices,
                                default=Severity.INFO, db_index=True)
    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name="notifications",
        help_text="Null means the whole house.",
    )
    url = models.CharField(max_length=300, blank=True,
                           help_text="Where to go when the alert is tapped.")
    icon = models.CharField(max_length=40, blank=True)
    context = models.JSONField(default=dict, blank=True)

    # Deduplication: two identical reminders in one window collapse into one.
    dedupe_key = models.CharField(max_length=160, blank=True, db_index=True)

    read_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
        related_name="acknowledged_notifications",
    )

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["recipient", "read_at", "-created_at"]),
            models.Index(fields=["dedupe_key", "-created_at"]),
        ]

    def __str__(self):
        return f"[{self.severity}] {self.title}"

    @property
    def is_unread(self) -> bool:
        return self.read_at is None


class Delivery(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"
        SKIPPED = "skipped", "Skipped"

    notification = models.ForeignKey(Notification, on_delete=models.CASCADE,
                                     related_name="deliveries")
    channel = models.CharField(max_length=20, db_index=True)
    target = models.CharField(max_length=120, blank=True,
                              help_text="Channel name, Slack user id, display slug…")
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    attempts = models.PositiveSmallIntegerField(default=0)
    error = models.TextField(blank=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    provider_ref = models.CharField(max_length=120, blank=True,
                                    help_text="Slack ts, message id, etc.")

    class Meta:
        ordering = ["-created_at"]
        verbose_name_plural = "deliveries"

    def __str__(self):
        return f"{self.channel} → {self.status}"
