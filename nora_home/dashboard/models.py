"""
Who put what where.

A layout is one person's arrangement of widgets. Everyone gets their own, plus
there is a shared "wall" layout the always-on display uses, so the living-room
screen does not inherit whatever someone last dragged around on their phone.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from nora_home.core.models import TimeStampedModel

# Sensible first screen for someone who has not arranged anything yet. These were
# the tracker's Today/Overdue/Reliability widgets until Story 40 deleted it;
# Todo's are the successors, and a key that no longer resolves is skipped at
# render time (see the class docstring below), so anyone still carrying a stored
# layout full of tracker.* keys sees those tiles quietly disappear rather than
# getting an error page.
#
# Sizes pack to whole rows — 6+3+3, then 12 — which is the point of the size
# system (Story 48): every size is a whole number of cells on a 12-column grid,
# so no arrangement can leave a ragged gap. Before that, widths were arbitrary
# (w, h) pairs and matching them across a row by hand was the only way to stop
# a screen reading as uneven.
STARTER_LAYOUT = [
    {"key": "todo.DueNextWidget", "size": "L"},
    {"key": "todo.OpenLoadWidget", "size": "S"},
    {"key": "core.HouseHealthWidget", "size": "S"},
    {"key": "todo.CompletionHeatmapWidget", "size": "XL"},
]


class DashboardLayout(TimeStampedModel):
    """One arrangement of widgets on a grid.

    `items` is an **ordered** list of {"key", "size"}, where size is one of
    S/M/L/XL (nora_home.dashboard.widgets.SIZES). Order is the layout: CSS grid
    places the tiles with `grid-auto-flow: row dense`, so there are no stored
    coordinates to go stale and no arrangement that can leave a ragged gap.
    Story 48 replaced the old {"x", "y", "w", "h"} form; migration 0003 carries
    existing layouts across.

    A key that no longer resolves (app uninstalled, widget renamed) is skipped at
    render time rather than deleted, so reinstalling the app restores the layout.
    """

    class Surface(models.TextChoices):
        PERSONAL = "personal", "Personal home screen"
        WALL = "wall", "Wall display"
        SHARED = "shared", "Shared house screen"

    member = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.CASCADE,
        related_name="dashboard_layouts",
        help_text="Null for shared and wall layouts.")
    surface = models.CharField(max_length=10, choices=Surface.choices,
                               default=Surface.PERSONAL)
    name = models.CharField(max_length=60, default="Home")
    items = models.JSONField(default=list, blank=True)
    is_default = models.BooleanField(default=True)

    class Meta:
        ordering = ["surface", "name"]
        unique_together = [("member", "surface", "name")]

    def __str__(self):
        return f"{self.member or 'house'} · {self.name}"

    @classmethod
    def for_member(cls, member) -> "DashboardLayout":
        layout, created = cls.objects.get_or_create(
            member=member, surface=cls.Surface.PERSONAL, name="Home",
            defaults={"items": list(STARTER_LAYOUT)},
        )
        return layout

    @classmethod
    def for_wall(cls) -> "DashboardLayout":
        layout, _ = cls.objects.get_or_create(
            member=None, surface=cls.Surface.WALL, name="Wall",
            defaults={"items": list(STARTER_LAYOUT)},
        )
        return layout

    @classmethod
    def for_shared(cls) -> "DashboardLayout":
        """The "Everyone" switcher tile's layout — one arrangement the whole
        house edits together, distinct from the wall's own."""
        layout, _ = cls.objects.get_or_create(
            member=None, surface=cls.Surface.SHARED, name="Everyone",
            defaults={"items": list(STARTER_LAYOUT)},
        )
        return layout

    def keys(self) -> list[str]:
        return [item.get("key", "") for item in self.items if item.get("key")]
