"""
The reference house app: habits with streaks.

Read this alongside DEVELOPMENT.md. It is deliberately small but touches every part
of the platform an app is likely to need — registry, tracker, notifications,
telemetry, cards, a wall panel, an MCP tool, and a Celery task.

Copy this directory, rename it, and delete what you don't need.
"""

from nora_home.core.registry import Category, NoraAppConfig


class ExampleHabitConfig(NoraAppConfig):
    # Standard Django AppConfig fields.
    name = "houseapps.example_habit"
    label = "example_habit"
    verbose_name = "Habits"

    # What the platform needs to place the app in the house.
    nora_slug = "habits"
    nora_title = "Habits"
    nora_description = "Small things done daily. Streaks, nudges, and a wall panel."
    nora_icon = "repeat"
    nora_category = Category.SELF
    nora_order = 10

    # Visualizations offered to the home screen, and panels for the 24" wall.
    nora_widgets = [
        "houseapps.example_habit.widgets.StreakWidget",
        "houseapps.example_habit.widgets.ConsistencyWidget",
    ]
    nora_wall_panels = ["houseapps.example_habit.cards.HabitWallPanel"]

    # Declared so the app directory and the MCP listing tell the truth.
    nora_provides_mcp_tools = True
    nora_owns_telemetry_series = ["habits.completion_rate"]

    def ready(self):
        # Importing these registers the signal receivers and the MCP tool. Keep it
        # to imports — anything that touches the database here runs before
        # migrations and will break `manage.py migrate` on a fresh install.
        from houseapps.example_habit import mcp_tools, signals  # noqa: F401
