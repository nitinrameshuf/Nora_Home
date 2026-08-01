"""
The wall panel.

Cards are the 24" display's unit; widgets (see widgets.py) are the home screen's.
They are separate because the wall renders full-screen HTML on a timer with nobody
touching it, while the home screen is an interactive grid of data. Keep `context()`
cheap — this re-renders forever.
"""

from __future__ import annotations

from django.utils import timezone

from nora_home.core.cards import Card
from nora_home.tracker.models import Occurrence


class HabitWallPanel(Card):
    title = "Streaks"
    template = "example_habit/panels/wall_streaks.html"
    size = "full"
    order = 30
    refresh_seconds = 300

    def context(self, request):  # noqa: ARG002
        from houseapps.example_habit.models import Habit

        rows = []
        for habit in Habit.objects.filter(is_active=True,
                                          owner__is_on_wall_display=True):
            trackable = _trackable_for(habit)
            rows.append({
                "owner": habit.owner.name,
                "title": habit.title,
                "streak": trackable.current_streak() if trackable else 0,
                "done_today": _is_done_today(habit),
            })
        rows.sort(key=lambda r: -r["streak"])
        return {"rows": rows[:12]}


def _trackable_for(habit):
    from nora_home.tracker.models import Trackable

    return Trackable.objects.filter(app_slug="habits",
                                    source_ref=str(habit.pk)).first()


def _is_done_today(habit) -> bool:
    return Occurrence.objects.filter(
        trackable__app_slug="habits",
        trackable__source_ref=str(habit.pk),
        status=Occurrence.Status.DONE,
        completed_at__date=timezone.localdate(),
    ).exists()
