"""
Making this app's data available to AI agents.

Once registered, `habit_streaks` shows up in `manage.py mcp_stdio` and at
/mcp/tools/, so Claude Code, Claude Desktop, or the robot can ask about it.
"""

from __future__ import annotations

from nora_home.mcpserver.registry import mcp_tool


@mcp_tool(
    name="habit_streaks",
    description=(
        "Current habit streaks for a member — what they are trying to keep up and "
        "how many consecutive days they have managed. Call this when asked how "
        "someone's routines are going, or before suggesting a new habit, so you can "
        "see what they are already carrying."
    ),
    schema={
        "type": "object",
        "properties": {
            "member": {"type": "string", "description": "Username; omit for everyone."},
        },
    },
    app_slug="habits",
)
def habit_streaks(member: str = "", **_):
    from houseapps.example_habit.models import Habit
    from nora_home.tracker.models import Trackable

    habits = Habit.objects.filter(is_active=True).select_related("owner")
    if member:
        habits = habits.filter(owner__username=member)

    results = []
    for habit in habits:
        trackable = Trackable.objects.filter(app_slug="habits",
                                             source_ref=str(habit.pk)).first()
        results.append({
            "member": habit.owner.get_username(),
            "habit": habit.title,
            "why": habit.why,
            "cadence": habit.cadence,
            "streak_days": trackable.current_streak() if trackable else 0,
        })
    return sorted(results, key=lambda r: -r["streak_days"])
