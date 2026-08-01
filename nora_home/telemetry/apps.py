from nora_home.core.registry import Category, NoraAppConfig


class TelemetryConfig(NoraAppConfig):
    name = "nora_home.telemetry"
    label = "telemetry"
    verbose_name = "Telemetry"

    nora_slug = "telemetry"
    nora_title = "Measurements"
    nora_description = ("Every number the house tracks over time — body, robot, "
                        "sensors, money.")
    nora_icon = "chart"
    nora_category = Category.SYSTEM
    nora_order = 35
    nora_url_prefix = "home/measurements/"
    nora_provides_mcp_tools = True
