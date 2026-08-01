from nora_home.core.registry import Category, NoraAppConfig


class DashboardConfig(NoraAppConfig):
    name = "nora_home.dashboard"
    label = "dashboard"
    verbose_name = "Dashboard"

    nora_slug = "dashboard"
    nora_title = "Dashboard"
    nora_description = "The home screen — visualizations picked from every app."
    nora_icon = "grid"
    nora_category = Category.SYSTEM
    nora_nav = False
    nora_url_prefix = "home/"
    nora_order = 2
