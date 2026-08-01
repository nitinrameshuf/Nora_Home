from nora_home.core.registry import Category, NoraAppConfig


class TrackerConfig(NoraAppConfig):
    name = "nora_home.tracker"
    label = "tracker"
    verbose_name = "Tracker"

    nora_slug = "tracker"
    nora_title = "Tracker"
    nora_description = ("Anything that has to happen, when it has to happen, "
                        "and who hears about it when it doesn't.")
    nora_icon = "target"
    nora_category = Category.SYSTEM
    nora_order = 5
    nora_url_prefix = "home/tracker/"
    nora_widgets = [
        "nora_home.tracker.widgets.TodayWidget",
        "nora_home.tracker.widgets.OverdueWidget",
        "nora_home.tracker.widgets.ReliabilityWidget",
        "nora_home.tracker.widgets.StreakWidget",
    ]
    nora_wall_panels = ["nora_home.tracker.cards.WallAgendaPanel"]
    nora_provides_mcp_tools = True
