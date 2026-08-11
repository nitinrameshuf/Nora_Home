from nora_home.core.registry import Category, NoraAppConfig


class CoreConfig(NoraAppConfig):
    name = "nora_home.core"
    label = "core"
    verbose_name = "Nora Core"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "core"
    nora_title = "Home"
    nora_description = "Dashboard, app registry, and system health."
    nora_icon = "home"
    nora_category = Category.SYSTEM
    nora_nav = False  # the dashboard is the root URL, not a nav entry
    nora_url_prefix = "home/"
    nora_order = 0
    nora_widgets = [
        "nora_home.core.widgets.HouseHealthWidget",
        "nora_home.core.widgets.CpuTemperatureWidget",
        "nora_home.core.widgets.DiskWidget",
    ]
    # Story 57 — matches the mockup's own Home REGISTRY entry exactly:
    # rearrange fits a physical key (it's a pure state toggle), add-widget
    # does not (it opens a picker that needs a choice).
    nora_actions = [
        {"verb": "rearrange", "title": "Rearrange", "kiosk": True},
        {"verb": "add-widget", "title": "Add a widget", "kiosk": False},
    ]

    def ready(self):
        from nora_home.core import signals  # noqa: F401
