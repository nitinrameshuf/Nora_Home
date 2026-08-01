from nora_home.core.registry import Category, NoraAppConfig


class DisplaysConfig(NoraAppConfig):
    name = "nora_home.displays"
    label = "displays"
    verbose_name = "Displays"

    nora_slug = "displays"
    nora_title = "Displays"
    nora_description = ("The always-on 24\" wall screen and the 10.1\" kiosk that "
                        "drives it.")
    nora_icon = "monitor"
    nora_category = Category.HOUSE
    nora_order = 15
    nora_url_prefix = "home/displays/"
