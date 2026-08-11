from nora_home.core.registry import Category, NoraAppConfig


class TelemetryConfig(NoraAppConfig):
    name = "nora_home.telemetry"
    label = "telemetry"
    verbose_name = "Telemetry"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "telemetry"
    nora_title = "Measurements"
    nora_description = ("Every number the house tracks over time — body, robot, "
                        "sensors, money.")
    nora_icon = "chart"
    nora_category = Category.HOUSE
    nora_order = 35
    nora_url_prefix = "home/measurements/"
    # Not a nav destination (Story 55) — the mockup's System page has no
    # standalone Measurements entry, only a tab (SYS_VIEWS.measurements).
    # index() redirects there; detail pages stay real and reachable by URL.
    nora_nav = False
    nora_provides_mcp_tools = True
    nora_widgets = ["nora_home.telemetry.widgets.HouseVitalsWidget"]
