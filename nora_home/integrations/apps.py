from nora_home.core.registry import Category, NoraAppConfig


class IntegrationsConfig(NoraAppConfig):
    name = "nora_home.integrations"
    label = "integrations"
    verbose_name = "Integrations"

    nora_slug = "integrations"
    nora_title = "Integrations"
    nora_description = ("Home Assistant, markets, calendars — anything outside the "
                        "house that the house should know about.")
    nora_icon = "link"
    nora_category = Category.INTEGRATIONS
    nora_order = 10
    nora_url_prefix = "home/integrations/"
