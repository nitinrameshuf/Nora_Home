"""
Telemetry widgets — what's true across every app's numbers right now.

HouseVitalsWidget is the telemetry-side counterpart to
nora_home.tracker.widgets.TodayWidget: it queries every active Series with no
app_slug filter, the same way TodayWidget queries every open Occurrence with
no app_slug filter. Any app that records through telemetry.record_reading()
shows up here automatically — nothing to register beyond define_series()
itself.
"""

from __future__ import annotations

from django.db.models import Q
from django.urls import reverse

from nora_home.core.registry import scope_members
from nora_home.dashboard.widgets import ListWidget
from nora_home.telemetry.models import Series


class HouseVitalsWidget(ListWidget):
    title = "House vitals"
    subtitle = "Every number, across every app"
    description = ("The latest reading from every measurement series in the "
                   "house, grouped by category — not just this app's own.")
    icon = "activity"
    default_size = (4, 5)
    refresh_seconds = 120
    empty_message = "Nothing measured yet."

    def rows(self, request):
        members = scope_members(request)
        series = (Series.objects
                 .filter(is_active=True)
                 .filter(Q(member__isnull=True) | Q(member__in=members))
                 .order_by("category", "app_slug", "label")
                 .select_related("member"))

        rows = []
        for s in series:
            reading = s.latest()
            if reading is None:
                continue
            status = s.classify(reading.value)
            group = s.category or s.app_slug
            rows.append({
                "title": s.label,
                "meta": (f"{group} · {reading.value:.{s.precision}f}{s.unit}"),
                "status": status,
                "url": reverse("telemetry:detail", args=[s.key]),
            })
        return rows
