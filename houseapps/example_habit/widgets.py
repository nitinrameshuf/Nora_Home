"""
Widgets this app offers the home screen.

Two of the four kinds, to show the shape: a list, and a chart. Read them next to
DEVELOPMENT.md — between them they cover most of what a house app will ever need.
"""

from __future__ import annotations

from django.utils import timezone

from nora_home.core.registry import scope_members
from nora_home.dashboard.widgets import ChartWidget, ListWidget
from nora_home.tracker.models import Occurrence, Trackable


class StreakWidget(ListWidget):
    title = "Habits"
    subtitle = "Longest runs first"
    description = "Each habit you are keeping up, and how many days you've managed."
    icon = "repeat"
    default_size = (4, 4)
    order = 20
    refresh_seconds = 600
    empty_message = "No habits yet. Add one in the admin."

    def is_visible(self, request):
        from houseapps.example_habit.models import Habit

        return Habit.objects.filter(owner__in=scope_members(request),
                                    is_active=True).exists()

    def rows(self, request):
        from houseapps.example_habit.models import Habit

        today = timezone.localdate()
        rows = []

        for habit in Habit.objects.filter(owner__in=scope_members(request),
                                          is_active=True):
            trackable = Trackable.objects.filter(app_slug="habits",
                                                 source_ref=str(habit.pk)).first()
            streak = trackable.current_streak() if trackable else 0
            done_today = Occurrence.objects.filter(
                trackable=trackable, status=Occurrence.Status.DONE,
                completed_at__date=today).exists() if trackable else False

            rows.append({
                "title": habit.title,
                "meta": (f"{streak} day streak" if streak else "not started")
                        + (" · done today" if done_today else ""),
                "status": "ok" if done_today else "",
                "url": f"/habits/{habit.uuid}/",
                "_streak": streak,
            })

        rows.sort(key=lambda row: -row["_streak"])
        for row in rows:
            row.pop("_streak")
        return rows


class ConsistencyWidget(ChartWidget):
    title = "Habit consistency"
    subtitle = "Last 8 weeks"
    description = "What share of your habits you completed each week."
    icon = "chart"
    default_size = (6, 3)
    order = 25
    refresh_seconds = 900

    def option(self, request):
        weeks, rates = [], []
        today = timezone.localdate()

        for offset in range(7, -1, -1):
            start = today - timezone.timedelta(days=today.weekday() + offset * 7)
            end = start + timezone.timedelta(days=7)
            window = Occurrence.objects.filter(
                trackable__app_slug="habits",
                trackable__owner__in=scope_members(request),
                due_at__date__gte=start, due_at__date__lt=end)

            done = window.filter(status=Occurrence.Status.DONE).count()
            missed = window.filter(status=Occurrence.Status.MISSED).count()
            total = done + missed

            weeks.append(start.strftime("%d %b"))
            # None rather than 0 for a week with nothing scheduled: a gap in the
            # line is honest, a zero says "you failed" when nothing was due.
            rates.append(round(done / total * 100) if total else None)

        return {
            "xAxis": {"type": "category", "data": weeks},
            "yAxis": {"type": "value", "max": 100, "name": "%"},
            "series": [{"type": "line", "data": rates, "connectNulls": True,
                        "areaStyle": {"opacity": 0.15}}],
        }
