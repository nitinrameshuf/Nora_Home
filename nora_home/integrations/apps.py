from nora_home.core.registry import Category, NoraAppConfig


class IntegrationsConfig(NoraAppConfig):
    name = "nora_home.integrations"
    label = "integrations"
    verbose_name = "Integrations"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "integrations"
    nora_title = "Integrations"
    nora_description = ("Home Assistant, markets, calendars — anything outside the "
                        "house that the house should know about.")
    nora_icon = "link"
    nora_category = Category.INTEGRATIONS
    nora_order = 10
    nora_url_prefix = "home/integrations/"
    # Not a nav destination (Story 55) — the mockup's System page has no
    # standalone Integrations entry, only a tab (SYS_VIEWS.integrations).
    # index() redirects there; detail pages stay real and reachable by URL.
    nora_nav = False

    def ready(self):
        from nora_home.integrations import providers  # noqa: F401
