from nora_home.core.registry import Category, NoraAppConfig


class NotificationsConfig(NoraAppConfig):
    name = "nora_home.notifications"
    label = "notifications"
    verbose_name = "Notifications"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "notifications"
    nora_title = "Alerts"
    nora_description = "Slack, in-app, and on-screen alerts, with delivery receipts."
    nora_icon = "bell"
    # Rendered manually as "Alerts" above the app-registry nav loop in base.html
    # (with a bell/count badge), not through the loop itself — this category
    # only matters so it doesn't leave a stray, empty "System" group behind.
    nora_category = Category.HOUSE
    nora_order = 20
    nora_url_prefix = "home/alerts/"
