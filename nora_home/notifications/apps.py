from nora_home.core.registry import Category, NoraAppConfig


class NotificationsConfig(NoraAppConfig):
    name = "nora_home.notifications"
    label = "notifications"
    verbose_name = "Notifications"

    nora_slug = "notifications"
    nora_title = "Alerts"
    nora_description = "Slack, in-app, and on-screen alerts, with delivery receipts."
    nora_icon = "bell"
    nora_category = Category.SYSTEM
    nora_order = 20
    nora_url_prefix = "home/alerts/"
