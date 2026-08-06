from nora_home.core.registry import Category, NoraAppConfig


class TrackerConfig(NoraAppConfig):
    name = "nora_home.tracker"
    label = "tracker"
    verbose_name = "Tracker"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "tracker"
    nora_title = "Tracker"
    nora_description = ("Anything that has to happen, when it has to happen, "
                        "and who hears about it when it doesn't.")
    nora_icon = "target"
    nora_category = Category.SYSTEM
    nora_order = 5
    nora_url_prefix = "home/tracker/"
    # No nav link — the Today/Overdue/Reliability cards it powers on the Home
    # dashboard are how the house actually uses this, not a standalone page.
    nora_nav = False
    nora_widgets = [
        "nora_home.tracker.widgets.TodayWidget",
        "nora_home.tracker.widgets.OverdueWidget",
        "nora_home.tracker.widgets.ReliabilityWidget",
        "nora_home.tracker.widgets.StreakWidget",
    ]
    # WallAgendaPanel (cards.py) is orphaned as of the nora_wall_panels removal
    # (Story 28) — nothing has rendered a wall panel since the wall was
    # repointed at the live app. Left in place; the whole tracker is deleted
    # in Story 40 when Todo absorbs it.
    nora_provides_mcp_tools = True
