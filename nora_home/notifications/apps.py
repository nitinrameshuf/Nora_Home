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
    # Rendered through the same flat "Apps" nav loop as every other nav=True
    # app (Story 47), just with a bell/count badge appended — base.html
    # special-cases the slug for that one addition, nothing more. category
    # still matters for navigation()'s other consumer, the wall dashboard's
    # one-column-per-category layout.
    nora_category = Category.HOUSE
    nora_order = 20
    nora_url_prefix = "home/alerts/"
