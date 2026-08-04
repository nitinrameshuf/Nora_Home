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
    nora_order = 2
    # Mounted for real at home/dashboard/ (widget catalog/layout/data
    # endpoints, used by dashboard.js — not for browsing), but its own ""
    # route renders the exact same view as core's "/home/" — so as a
    # directory entry it would just be Home's page under a second name.
    nora_has_page = False
