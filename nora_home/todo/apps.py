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

    # open_items and member_reliability, inherited from the tracker in Story 40.
    nora_provides_mcp_tools = True
    nora_has_page = True
    nora_nav = True

    def ready(self):
        from nora_home.todo import system_tasks  # noqa: F401 — connects the signal receivers

        # Registers `/todo` and its message buttons. Same reason as above: the
        # Socket Mode process dispatches through a registry it expects to find
        # already populated, so the base platform never imports this app by name.
        from nora_home.todo import slack_commands  # noqa: F401

        # Importing the module is what registers the tools, exactly as
        # nora_home.mcpserver.apps does for the platform's own.
        from nora_home.todo import mcp_tools  # noqa: F401

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

    # What the sidebar shows while you are inside Todo, and — Story 55 — the
    # kiosk's own key bank now too: the mockup's WALL_APPS derives a kiosk
    # app's `controls` directly from its `sections`, every one, not a curated
    # subset (ui-overhaul-mockup.html: `controls: a.sections.map(...)`).
    # This file used to carry a second, shorter "five big touch targets"
    # list here — a real, working decision from Story 50, but not what the
    # mockup actually specifies, and found live by direct comparison rather
    # than assumed still correct. "Tasks" is also renamed to "Board" to match
    # REGISTRY's own title for this section exactly.
    nora_sections = [
        {"title": "Board", "path": "/todo/"},
        {"title": "Calendar", "path": "/todo/calendar/"},
        {"title": "Search", "path": "/todo/search/"},
        {"title": "Labels", "path": "/todo/labels/"},
        {"title": "Reporting", "path": "/todo/reporting/"},
        {"title": "System", "path": "/todo/system/"},
        {"title": "Settings", "path": "/todo/settings/"},
    ]

    nora_kiosk_controls = nora_sections

    # Story 57. The mockup's own REGISTRY also declares complete-next and
    # snooze-next for Todo, both kiosk:true — deliberately not carried over
    # here. Neither has a real handler in this app today (no "complete the
    # next due task" or "snooze it an hour" entry point exists anywhere,
    # kiosk or otherwise), and inventing one would be new product behaviour
    # nobody has approved, not a declare-once-derive-everywhere refactor.
    # new-task is kiosk:false on purpose too: since Story 53, creating a task
    # means picking a priority column, and picking a column is a choice — the
    # same rule that keeps "Add a widget" off the kiosk.
    nora_actions = [
        {"verb": "new-task", "title": "New task", "kiosk": False},
    ]
