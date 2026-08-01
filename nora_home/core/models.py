"""
Base models every app should build on, plus platform-level records.

TimeStampedModel and OwnedModel exist so that "who touched this and when" is
answerable for anything in the house without each app reinventing it.
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """Inherit this for anything persistent. Non-negotiable for house apps."""

    created_at = models.DateTimeField(default=timezone.now, editable=False, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        get_latest_by = "created_at"


class OwnedModel(TimeStampedModel):
    """Anything belonging to a specific person in the house."""

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        db_index=True,
    )

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    """For records referenced from outside the DB (object storage keys, QR codes,
    device payloads) where a guessable integer id would be a nuisance."""

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    def alive(self):
        return self.filter(deleted_at__isnull=True)

    def dead(self):
        return self.filter(deleted_at__isnull=False)

    def delete(self):
        return self.update(deleted_at=timezone.now())


class SoftDeleteModel(models.Model):
    """Nothing in a house should vanish irrecoverably by accident."""

    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):  # noqa: ARG002
        self.deleted_at = timezone.now()
        self.save(update_fields=["deleted_at"])

    def hard_delete(self, using=None):
        return super().delete(using=using)

    def restore(self):
        self.deleted_at = None
        self.save(update_fields=["deleted_at"])


class HouseSetting(TimeStampedModel):
    """Runtime configuration a family member can change without a deploy.

    Read via nora_home.core.settings_store.get_setting(). Secrets belong in .env, not here.
    """

    key = models.CharField(max_length=120, unique=True)
    value = models.JSONField(default=dict, blank=True)
    app_slug = models.CharField(max_length=60, blank=True, db_index=True)
    description = models.CharField(max_length=255, blank=True)
    editable_by_role = models.CharField(max_length=20, default="adult")

    class Meta:
        ordering = ["app_slug", "key"]

    def __str__(self):
        return self.key


class AuditEvent(TimeStampedModel):
    """A durable record of things that mattered. Written by
    nora_home.core.audit.record(); never edited afterwards."""

    class Severity(models.TextChoices):
        DEBUG = "debug", "Debug"
        INFO = "info", "Info"
        NOTICE = "notice", "Notice"
        WARNING = "warning", "Warning"
        ALERT = "alert", "Alert"

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_events",
    )
    app_slug = models.CharField(max_length=60, db_index=True)
    action = models.CharField(max_length=120, db_index=True)
    severity = models.CharField(max_length=10, choices=Severity.choices,
                                default=Severity.INFO, db_index=True)
    subject = models.CharField(max_length=255, blank=True)
    detail = models.JSONField(default=dict, blank=True)
    source = models.CharField(max_length=60, blank=True)  # web | kiosk | celery | mcp | api

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["app_slug", "action", "-created_at"])]

    def __str__(self):
        return f"{self.app_slug}:{self.action}"


class SystemHealthSnapshot(TimeStampedModel):
    """Periodic vitals for the Pi and its dependencies. Powers /health and the
    System panel on the wall display."""

    cpu_percent = models.FloatField(null=True, blank=True)
    memory_percent = models.FloatField(null=True, blank=True)
    disk_percent = models.FloatField(null=True, blank=True)
    cpu_temp_c = models.FloatField(null=True, blank=True)
    uptime_seconds = models.BigIntegerField(null=True, blank=True)
    services = models.JSONField(default=dict, blank=True)  # {"mysql": "ok", ...}
    healthy = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"health @ {self.created_at:%Y-%m-%d %H:%M}"


class DeviceToken(TimeStampedModel):
    """Long-lived token for a non-browser client: the wall display, the kiosk, the
    Nora robot, a phone shortcut. Scoped and revocable."""

    name = models.CharField(max_length=80)
    token_hash = models.CharField(max_length=128, unique=True)
    prefix = models.CharField(max_length=12, db_index=True)
    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.CASCADE, related_name="device_tokens",
    )
    scopes = models.JSONField(default=list, blank=True)  # ["telemetry:write", "read"]
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
