"""
The tracker — the platform's answer to "did this actually happen?".

Three layers, deliberately separate:

  Trackable   the standing intent ("change the water filter every 3 months")
  Occurrence  one concrete due instance, materialized ahead of time
  Completion  evidence that a specific occurrence was done, by whom, when

House apps do not need their own reminder logic. They create a Trackable pointing
back at their own record via (source_app, source_ref) and let the platform handle
due dates, nudges, escalation, and streaks. See docs/Main_App/DEVELOPMENT.md.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from nora_home.core.models import SoftDeleteModel, TimeStampedModel, UUIDModel


class Cadence(models.TextChoices):
    ONCE = "once", "One time"
    DAILY = "daily", "Daily"
    WEEKDAYS = "weekdays", "Weekdays"
    WEEKLY = "weekly", "Weekly"
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    YEARLY = "yearly", "Yearly"
    INTERVAL = "interval", "Every N days"
    CRON = "cron", "Cron expression"


class EscalationPolicy(TimeStampedModel):
    """How hard the house pushes when something is not done.

    `levels` is an ordered list of rungs, each escalating further:

        [
          {"after_minutes": 0,    "notify": "owner",  "severity": "nudge"},
          {"after_minutes": 120,  "notify": "owner",  "severity": "warning"},
          {"after_minutes": 720,  "notify": "chain",  "severity": "alert"},
          {"after_minutes": 2880, "notify": "house",  "severity": "critical"}
        ]

    notify: owner | chain (the member's escalation_contacts, one rung per level)
            | adults | house
    """

    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=200, blank=True)
    grace_minutes = models.PositiveIntegerField(
        default=0, help_text="Time after due before the first rung fires.")
    levels = models.JSONField(default=list)
    stop_on_acknowledge = models.BooleanField(
        default=True, help_text="Acknowledging the alert halts further rungs.")
    quiet_hours_respected = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)

    class Meta:
        verbose_name_plural = "escalation policies"
        ordering = ["name"]

    def __str__(self):
        return self.name

    @classmethod
    def get_default(cls) -> "EscalationPolicy":
        policy = cls.objects.filter(is_default=True).first()
        if policy:
            return policy
        return cls.objects.create(
            name="House default",
            description="Nudge, warn, tell the household, then tell everyone.",
            grace_minutes=15,
            is_default=True,
            levels=[
                {"after_minutes": 0, "notify": "owner", "severity": "nudge"},
                {"after_minutes": 120, "notify": "owner", "severity": "warning"},
                {"after_minutes": 720, "notify": "chain", "severity": "alert"},
                {"after_minutes": 2880, "notify": "house", "severity": "critical"},
            ],
        )


class Trackable(UUIDModel, SoftDeleteModel, TimeStampedModel):
    """A standing thing that should keep happening."""

    class Kind(models.TextChoices):
        TASK = "task", "Task"
        HABIT = "habit", "Habit"
        MAINTENANCE = "maintenance", "Maintenance"
        GOAL = "goal", "Goal milestone"
        MEASUREMENT = "measurement", "Measurement"
        CHECKIN = "checkin", "Check-in"

    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True)
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.TASK)

    # Ownership and provenance.
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                              related_name="trackables")
    app_slug = models.CharField(max_length=60, db_index=True, default="tracker",
                                help_text="The app that owns this trackable.")
    source_ref = models.CharField(max_length=120, blank=True, db_index=True,
                                  help_text="The app's own id for the underlying record.")
    url = models.CharField(max_length=300, blank=True,
                           help_text="Deep link into the owning app.")

    # Scheduling.
    cadence = models.CharField(max_length=12, choices=Cadence.choices,
                               default=Cadence.ONCE)
    interval_days = models.PositiveIntegerField(null=True, blank=True)
    cron_expression = models.CharField(max_length=100, blank=True)
    due_time = models.TimeField(null=True, blank=True,
                                help_text="Local time of day an occurrence is due.")
    starts_on = models.DateField(default=timezone.localdate)
    ends_on = models.DateField(null=True, blank=True)
    next_due_at = models.DateTimeField(null=True, blank=True, db_index=True)

    # Behaviour.
    escalation_policy = models.ForeignKey(EscalationPolicy, null=True, blank=True,
                                          on_delete=models.SET_NULL,
                                          related_name="trackables")
    requires_evidence = models.BooleanField(
        default=False, help_text="Completion must include a note, number, or photo.")
    evidence_label = models.CharField(max_length=60, blank=True)
    allow_skip = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True, db_index=True)
    show_on_wall = models.BooleanField(default=True)
    priority = models.PositiveSmallIntegerField(default=2,
                                                help_text="1 high, 2 normal, 3 low.")
    tags = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["priority", "next_due_at", "title"]
        indexes = [
            models.Index(fields=["app_slug", "source_ref"]),
            models.Index(fields=["owner", "is_active", "next_due_at"]),
        ]

    def __str__(self):
        return self.title

    @property
    def policy(self) -> EscalationPolicy:
        return self.escalation_policy or EscalationPolicy.get_default()

    @property
    def is_recurring(self) -> bool:
        return self.cadence != Cadence.ONCE

    def current_streak(self) -> int:
        """Consecutive completed occurrences, newest first, until a miss."""
        streak = 0
        for occ in self.occurrences.filter(
            status__in=[Occurrence.Status.DONE, Occurrence.Status.MISSED]
        ).order_by("-due_at")[:365]:
            if occ.status == Occurrence.Status.DONE:
                streak += 1
            else:
                break
        return streak


class OccurrenceQuerySet(models.QuerySet):
    def open(self):
        return self.filter(status=Occurrence.Status.PENDING)

    def overdue(self, now=None):
        return self.open().filter(due_at__lt=now or timezone.now())

    def due_today(self):
        today = timezone.localdate()
        return self.open().filter(due_at__date=today)

    def for_member(self, member):
        return self.filter(trackable__owner=member)

    def for_members(self, members):
        return self.filter(trackable__owner__in=members)


class Occurrence(UUIDModel, TimeStampedModel):
    """One concrete instance of a Trackable falling due."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        DONE = "done", "Done"
        MISSED = "missed", "Missed"
        SKIPPED = "skipped", "Skipped"
        CANCELLED = "cancelled", "Cancelled"

    trackable = models.ForeignKey(Trackable, on_delete=models.CASCADE,
                                  related_name="occurrences")
    due_at = models.DateTimeField(db_index=True)
    window_ends_at = models.DateTimeField(
        null=True, blank=True,
        help_text="After this the occurrence is marked missed rather than left open.")
    status = models.CharField(max_length=10, choices=Status.choices,
                              default=Status.PENDING, db_index=True)

    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name="completed_occurrences")

    # Escalation bookkeeping.
    escalation_level = models.PositiveSmallIntegerField(default=0, db_index=True)
    last_escalated_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        related_name="acknowledged_occurrences")

    objects = OccurrenceQuerySet.as_manager()

    class Meta:
        ordering = ["due_at"]
        unique_together = [("trackable", "due_at")]
        indexes = [
            models.Index(fields=["status", "due_at"]),
            models.Index(fields=["status", "escalation_level", "due_at"]),
        ]

    def __str__(self):
        return f"{self.trackable.title} due {self.due_at:%Y-%m-%d %H:%M}"

    @property
    def is_overdue(self) -> bool:
        return self.status == self.Status.PENDING and self.due_at < timezone.now()

    @property
    def minutes_overdue(self) -> int:
        if not self.is_overdue:
            return 0
        return int((timezone.now() - self.due_at).total_seconds() // 60)

    def complete(self, member=None, *, note: str = "", value=None, evidence=None):
        """Mark done and record the evidence. Fires nora_home.core.signals.item_completed."""
        from nora_home.core.signals import item_completed

        self.status = self.Status.DONE
        self.completed_at = timezone.now()
        self.completed_by = member or self.trackable.owner
        self.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])

        completion = Completion.objects.create(
            occurrence=self, member=self.completed_by, note=note,
            numeric_value=value, evidence=evidence,
        )
        item_completed.send(sender=type(self), item=self,
                            member=self.completed_by, completion=completion)
        return completion

    def skip(self, member=None, reason: str = ""):
        self.status = self.Status.SKIPPED
        self.completed_at = timezone.now()
        self.completed_by = member
        self.save(update_fields=["status", "completed_at", "completed_by", "updated_at"])
        Completion.objects.create(occurrence=self, member=member, note=reason,
                                  was_skip=True)

    def acknowledge(self, member):
        """Stop the escalation ladder without claiming the work is done."""
        self.acknowledged_at = timezone.now()
        self.acknowledged_by = member
        self.save(update_fields=["acknowledged_at", "acknowledged_by", "updated_at"])


class Completion(TimeStampedModel):
    """Evidence. Kept separate from Occurrence so history survives re-opening."""

    occurrence = models.ForeignKey(Occurrence, on_delete=models.CASCADE,
                                   related_name="completions")
    member = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                               on_delete=models.SET_NULL, related_name="completions")
    note = models.TextField(blank=True)
    numeric_value = models.FloatField(null=True, blank=True,
                                      help_text="Reps, minutes, kg, dollars — app decides.")
    evidence = models.FileField(upload_to="tracker/evidence/%Y/%m/", null=True, blank=True)
    was_skip = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"completion of {self.occurrence_id}"


class EscalationEvent(TimeStampedModel):
    """An immutable record that the house pushed harder about something."""

    occurrence = models.ForeignKey(Occurrence, on_delete=models.CASCADE,
                                   related_name="escalations")
    level = models.PositiveSmallIntegerField()
    notified = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                      related_name="escalations_received")
    severity = models.CharField(max_length=10)
    audience = models.CharField(max_length=10)
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"L{self.level} on {self.occurrence_id}"
