"""Dashboard cards and the wall-display agenda panel."""

from __future__ import annotations

from django.utils import timezone

from nora_home.core.cards import Card
from nora_home.tracker.models import Occurrence


class TodayCard(Card):
    title = "Today"
    subtitle = "What you owe the house"
    template = "tracker/cards/today.html"
    icon = "sun"
    size = "medium"
    order = 10
    refresh_seconds = 120

    def context(self, request):
        end = timezone.localtime().replace(hour=23, minute=59, second=59)
        items = (Occurrence.objects.open()
                 .for_member(request.user)
                 .filter(due_at__lte=end)
                 .select_related("trackable")
                 .order_by("due_at")[:10])
        return {"items": items, "count": len(items)}


class OverdueCard(Card):
    title = "Overdue"
    subtitle = "Escalating soon"
    template = "tracker/cards/overdue.html"
    icon = "alert"
    size = "medium"
    order = 5
    refresh_seconds = 120

    def is_visible(self, request):
        return Occurrence.objects.overdue().for_member(request.user).exists()

    def context(self, request):
        items = (Occurrence.objects.overdue()
                 .for_member(request.user)
                 .select_related("trackable")
                 .order_by("due_at")[:10])
        return {"items": items}


class WallAgendaPanel(Card):
    """Full-screen panel for the always-on 24" display: the whole house at once."""

    title = "House agenda"
    template = "tracker/panels/wall_agenda.html"
    size = "full"
    order = 10
    refresh_seconds = 60

    def context(self, request):  # noqa: ARG002
        now = timezone.now()
        end_of_day = timezone.localtime(now).replace(hour=23, minute=59, second=59)
        items = (Occurrence.objects.open()
                 .filter(due_at__lte=end_of_day,
                         trackable__show_on_wall=True,
                         trackable__owner__is_on_wall_display=True)
                 .select_related("trackable", "trackable__owner")
                 .order_by("due_at")[:24])

        by_member: dict = {}
        for occurrence in items:
            by_member.setdefault(occurrence.trackable.owner, []).append(occurrence)

        return {
            "by_member": by_member,
            "overdue_count": sum(1 for i in items if i.due_at < now),
            "now": now,
        }
