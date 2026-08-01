"""
Habits.

Note what is *not* here: no due dates, no reminder logic, no escalation, no "did
they do it" table. All of that is the tracker's job. This model registers a
Trackable and lets the platform own the schedule — which is the pattern every
house app should follow.
"""

from __future__ import annotations

from django.db import models

from nora_home.core.models import OwnedModel, UUIDModel


class Habit(UUIDModel, OwnedModel):
    """One thing someone is trying to do consistently."""

    class Cadence(models.TextChoices):
        DAILY = "daily", "Every day"
        WEEKDAYS = "weekdays", "Weekdays"
        WEEKLY = "weekly", "Once a week"

    title = models.CharField(max_length=120)
    why = models.CharField(max_length=200, blank=True,
                           help_text="Shown in the nudge. 'Because my back hurts' "
                                     "works better than 'health'.")
    cadence = models.CharField(max_length=10, choices=Cadence.choices,
                               default=Cadence.DAILY)
    due_time = models.TimeField(null=True, blank=True)
    target_per_week = models.PositiveSmallIntegerField(default=7)
    is_active = models.BooleanField(default=True, db_index=True)

    class Meta:
        ordering = ["title"]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        """Keep the platform's trackable in step with this record.

        Doing it in save() means every path that creates a habit — the admin, a
        view, a fixture, the shell — gets scheduling and escalation automatically.
        `register_trackable` is idempotent on (app_slug, source_ref), so this
        updates rather than duplicating.
        """
        super().save(*args, **kwargs)

        from nora_home.tracker.api import deactivate_trackable, register_trackable

        if not self.is_active:
            deactivate_trackable(app_slug="habits", source_ref=str(self.pk))
            return

        register_trackable(
            owner=self.owner,
            title=self.title,
            app_slug="habits",
            source_ref=str(self.pk),
            cadence=self.cadence,
            kind="habit",
            notes=self.why,
            due_time=self.due_time,
            url=f"/app/habits/{self.uuid}/",
            escalation_policy="Gentle",
            priority=2,
        )
