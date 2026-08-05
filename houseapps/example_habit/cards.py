"""
The wall panel.

Cards are the 24" display's unit; widgets (see widgets.py) are the home screen's.
They are separate because the wall renders full-screen HTML on a timer with nobody
touching it, while the home screen is an interactive grid of data. Keep `context()`
cheap — this re-renders forever.
"""

from __future__ import annotations

from nora_home.core.cards import Card
from nora_home.tracker.api import is_done_today, streak_for


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
            ref = str(habit.pk)
            rows.append({
                "owner": habit.owner.name,
                "title": habit.title,
                "streak": streak_for(app_slug="habits", source_ref=ref),
                "done_today": is_done_today(app_slug="habits", source_ref=ref),
            })
        rows.sort(key=lambda r: -r["streak"])
        return {"rows": rows[:12]}
