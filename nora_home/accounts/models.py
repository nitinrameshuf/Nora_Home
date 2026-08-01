"""
The household.

HouseMember is the project's AUTH_USER_MODEL. Every app references people through
settings.AUTH_USER_MODEL — never through a name string.
"""

from __future__ import annotations

from django.contrib.auth.models import AbstractUser
from django.db import models

from nora_home.core.models import TimeStampedModel


class HouseMember(AbstractUser):
    """A person in the house.

    Roles control what a member can see and who escalations reach:
      member — kids and guests; sees their own apps and shared dashboards
      adult  — full house visibility; a valid escalation target
      admin  — plus settings, tokens, backups, and app management
    """

    class Role(models.TextChoices):
        MEMBER = "member", "Member"
        ADULT = "adult", "Adult"
        ADMIN = "admin", "Admin"

    display_name = models.CharField(max_length=60, blank=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.MEMBER,
                            db_index=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    accent_color = models.CharField(max_length=9, blank=True,
                                    help_text="Hex colour used for this person's rows.")
    birthday = models.DateField(null=True, blank=True)
    timezone = models.CharField(max_length=64, blank=True)

    # Contact endpoints for notifications and escalation.
    slack_user_id = models.CharField(max_length=32, blank=True,
                                     help_text="Slack member ID, e.g. U01ABCDEF.")
    slack_dm_channel = models.CharField(max_length=32, blank=True)
    phone = models.CharField(max_length=32, blank=True)

    # Notification preferences.
    quiet_hours_start = models.PositiveSmallIntegerField(default=22)
    quiet_hours_end = models.PositiveSmallIntegerField(default=7)
    notifications_enabled = models.BooleanField(default=True)
    preferred_channels = models.JSONField(default=list, blank=True)

    # Who hears about it when this person misses something. Ordered; the escalation
    # engine walks the list one level at a time.
    escalation_contacts = models.ManyToManyField(
        "self", symmetrical=False, blank=True, related_name="escalation_watch_for",
        through="EscalationContact",
    )

    is_on_wall_display = models.BooleanField(
        default=True, help_text="Show this person's items on the 24\" display.")

    class Meta:
        ordering = ["display_name", "username"]

    def __str__(self):
        return self.display_name or self.get_username()

    def save(self, *args, **kwargs):
        # Nothing in this house gates admin access with a password — role is the
        # only gate, so it has to imply the Django flags admin actually checks.
        if self.role == self.Role.ADMIN:
            self.is_staff = True
            self.is_superuser = True
        super().save(*args, **kwargs)

    @property
    def name(self) -> str:
        return self.display_name or self.get_full_name() or self.get_username()

    @property
    def is_adult(self) -> bool:
        return self.role in {self.Role.ADULT, self.Role.ADMIN}

    def in_quiet_hours(self, when=None) -> bool:
        from django.utils import timezone as dj_tz

        hour = (when or dj_tz.localtime()).hour
        start, end = self.quiet_hours_start, self.quiet_hours_end
        return start <= hour or hour < end if start > end else start <= hour < end

    def escalation_chain(self) -> list["HouseMember"]:
        links = (EscalationContact.objects
                 .filter(member=self)
                 .select_related("contact")
                 .order_by("level"))
        chain = [link.contact for link in links]
        if chain:
            return chain
        # Sensible default: every adult except this person.
        return list(HouseMember.objects.filter(role__in=[self.Role.ADULT, self.Role.ADMIN])
                    .exclude(pk=self.pk))


class EscalationContact(TimeStampedModel):
    """One rung on a member's escalation ladder."""

    member = models.ForeignKey(HouseMember, on_delete=models.CASCADE,
                               related_name="escalation_links")
    contact = models.ForeignKey(HouseMember, on_delete=models.CASCADE,
                                related_name="escalation_links_to")
    level = models.PositiveSmallIntegerField(default=1)
    note = models.CharField(max_length=140, blank=True)

    class Meta:
        ordering = ["member", "level"]
        unique_together = [("member", "contact")]

    def __str__(self):
        return f"{self.member} → L{self.level} {self.contact}"
