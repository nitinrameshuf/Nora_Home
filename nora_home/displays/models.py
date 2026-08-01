"""
The screens in the house.

The Pi 5 drives two: HDMI-0 goes to the 24" 1080p wall display that is always on,
HDMI-1 to the 10.1" touchscreen running in kiosk mode. The small one is a remote
control for the big one — it holds a websocket to the server, and the server relays
its commands to whichever display is addressed.

Modelling displays as rows (rather than hard-coding two) means a phone propped in
the kitchen or a tablet in the garage can register itself and join the rotation.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone

from nora_home.core.models import TimeStampedModel

# A display is considered offline if it has not sent a heartbeat in this long.
HEARTBEAT_GRACE_SECONDS = 90


class Display(TimeStampedModel):
    class Kind(models.TextChoices):
        WALL = "wall", "Wall display (always on)"
        KIOSK = "kiosk", "Kiosk controller"
        AMBIENT = "ambient", "Ambient / secondary"

    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=80)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.WALL)
    location = models.CharField(max_length=80, blank=True)

    width = models.PositiveIntegerField(default=1920)
    height = models.PositiveIntegerField(default=1080)

    # What it is showing, and whether it moves on by itself.
    current_panel = models.CharField(max_length=120, blank=True)
    rotation_enabled = models.BooleanField(default=True)
    rotation_seconds = models.PositiveIntegerField(default=45)
    pinned_until = models.DateTimeField(
        null=True, blank=True,
        help_text="Rotation pauses until this time — the kiosk sets it when someone "
                  "pins a panel to look at it.")

    # Screen behaviour.
    night_mode_start = models.PositiveSmallIntegerField(default=23)
    night_mode_end = models.PositiveSmallIntegerField(default=6)
    brightness = models.PositiveSmallIntegerField(default=100)

    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "name"]

    def __str__(self):
        return f"{self.name} ({self.slug})"

    @property
    def is_online(self) -> bool:
        if self.last_seen_at is None:
            return False
        age = (timezone.now() - self.last_seen_at).total_seconds()
        return age < HEARTBEAT_GRACE_SECONDS

    @property
    def is_pinned(self) -> bool:
        return self.pinned_until is not None and self.pinned_until > timezone.now()

    def in_night_mode(self) -> bool:
        hour = timezone.localtime().hour
        start, end = self.night_mode_start, self.night_mode_end
        return start <= hour or hour < end if start > end else start <= hour < end

    def touch(self):
        Display.objects.filter(pk=self.pk).update(last_seen_at=timezone.now())


class DisplayCommand(TimeStampedModel):
    """A record of what the kiosk asked a display to do.

    Kept because "why did the wall show the grocery list at 2am" should be
    answerable, and because a display that reconnects can replay the last command
    instead of showing a blank screen.
    """

    display = models.ForeignKey(Display, on_delete=models.CASCADE,
                                related_name="commands")
    action = models.CharField(max_length=40)  # show | pin | unpin | wake | sleep …
    payload = models.JSONField(default=dict, blank=True)
    issued_by = models.CharField(max_length=60, blank=True,
                                 help_text="Member username, 'kiosk', or 'celery'.")
    delivered = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.display_id}:{self.action}"
