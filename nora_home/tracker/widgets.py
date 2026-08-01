"""Tracker widgets — what the house owes, and how reliably it delivers."""

from __future__ import annotations

from django.urls import reverse
from django.utils import timezone

from nora_home.core.registry import scope_members
from nora_home.dashboard.widgets import ChartWidget, ListWidget, StatWidget
from nora_home.tracker.models import Occurrence


class TodayWidget(ListWidget):
    title = "Today"
    subtitle = "What you owe the house"
    description = "Everything of yours due before midnight, soonest first."
    icon = "sun"
    default_size = (4, 4)
    refresh_seconds = 120
    empty_message = "Nothing due today. Enjoy it."

    def rows(self, request):
        end_of_day = timezone.localtime().replace(hour=23, minute=59, second=59)
        items = (Occurrence.objects.open()
                 .for_members(scope_members(request))
                 .filter(due_at__lte=end_of_day)
                 .select_related("trackable")
                 .order_by("due_at")[:12])
        now = timezone.now()
        return [{
            "title": item.trackable.title,
            "meta": timezone.localtime(item.due_at).strftime("%H:%M"),
            "status": "alert" if item.due_at < now else "ok",
            "url": item.trackable.url or reverse("tracker:board"),
            "action_url": reverse("tracker:complete", args=[item.uuid]),
        } for item in items]


class OverdueWidget(ListWidget):
    title = "Overdue"
    subtitle = "Escalating"
    description = "Anything of yours past its due time, with its escalation level."
    icon = "alert"
    default_size = (4, 4)
    refresh_seconds = 120
    empty_message = "Nothing late. Good."

    def rows(self, request):
        items = (Occurrence.objects.overdue()
                 .for_members(scope_members(request))
                 .select_related("trackable")
                 .order_by("due_at")[:12])
        return [{
            "title": item.trackable.title,
            "meta": (f"{item.minutes_overdue // 60}h late"
                     if item.minutes_overdue >= 60
                     else f"{item.minutes_overdue}m late")
                    + (f" · L{item.escalation_level}" if item.escalation_level else ""),
            "status": "alert",
            "url": item.trackable.url or reverse("tracker:board"),
            "action_url": reverse("tracker:complete", args=[item.uuid]),
        } for item in items]


class ReliabilityWidget(ChartWidget):
    title = "Reliability"
    subtitle = "Completed vs missed, by week"
    description = "How consistently you finish what you take on, over 12 weeks."
    icon = "chart"
    default_size = (4, 4)
    refresh_seconds = 900

    def option(self, request):
        weeks, done, missed = [], [], []
        today = timezone.localdate()

        for offset in range(11, -1, -1):
            start = today - timezone.timedelta(days=today.weekday() + offset * 7)
            end = start + timezone.timedelta(days=7)
            window = Occurrence.objects.filter(
                trackable__owner__in=scope_members(request),
                due_at__date__gte=start, due_at__date__lt=end)

            weeks.append(start.strftime("%d %b"))
            done.append(window.filter(status=Occurrence.Status.DONE).count())
            missed.append(window.filter(status=Occurrence.Status.MISSED).count())

        return {
            "xAxis": {"type": "category", "data": weeks},
            "yAxis": {"type": "value"},
            "legend": {"data": ["Done", "Missed"]},
            "series": [
                {"name": "Done", "type": "bar", "stack": "total", "data": done},
                {"name": "Missed", "type": "bar", "stack": "total", "data": missed},
            ],
        }


class StreakWidget(StatWidget):
    title = "Open items"
    description = "How much the whole house currently has outstanding."
    icon = "target"
    default_size = (3, 2)
    refresh_seconds = 300

    def stat(self, request):  # noqa: ARG002
        open_count = Occurrence.objects.open().count()
        overdue = Occurrence.objects.overdue().count()
        return {
            "value": open_count,
            "label": "open across the house",
            "delta": f"{overdue} overdue" if overdue else "none overdue",
            "status": "alert" if overdue else "ok",
        }
