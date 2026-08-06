"""
Todo — the house's task system. Replaces the tracker (see
docs/Main_App/subsystems/todo.md); Level 2, not a house app.
"""

from nora_home.core.registry import Category, NoraAppConfig


class TodoConfig(NoraAppConfig):
    name = "nora_home.todo"
    label = "todo"
    verbose_name = "Todo"

    nora_slug = "todo"
    nora_title = "Todo"
    nora_description = "Everything that has to happen, when, and who hears about it."
    nora_icon = "check"
    nora_category = Category.SYSTEM
    # Level 2 — the base leans on this app (scheduling, reminders, escalation).
    # See docs/Main_App/subsystems/todo.md §1.
    nora_level = 2
    nora_order = 5
    nora_url_prefix = "todo/"

    # Still to come: nora_provides_mcp_tools + ready() importing mcp_tools.
    nora_has_page = True
    nora_nav = True

    # §6: widgets are for the *home screen*, not how Todo presents itself —
    # deliberately a small chosen set, not one per chart on Reporting.
    nora_widgets = [
        "nora_home.todo.widgets.OpenLoadWidget",
        "nora_home.todo.widgets.TypicalThroughputWidget",
        "nora_home.todo.widgets.StreakWidget",
        "nora_home.todo.widgets.DueNextWidget",
        "nora_home.todo.widgets.CompletionHeatmapWidget",
        "nora_home.todo.widgets.CumulativeFlowWidget",
    ]

    # §6: "Two levels, and both are required" — this is the second, the
    # buttons the kiosk shows once the wall has switched to Todo. Four of the
    # design doc's five: Reporting joined when Story 35 gave it a page to point
    # at. System tasks (Story 36) still has none, and a kiosk tile linking to a
    # 404 on a wall-mounted touchscreen is worse than a tile that isn't there.
    nora_kiosk_controls = [
        {"title": "Tasks", "path": "/todo/"},
        {"title": "Due today", "path": "/todo/?due=today"},
        {"title": "Calendar", "path": "/todo/calendar/"},
        {"title": "Reporting", "path": "/todo/reporting/"},
    ]
