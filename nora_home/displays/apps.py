from nora_home.core.registry import Category, NoraAppConfig


class DisplaysConfig(NoraAppConfig):
    name = "nora_home.displays"
    label = "displays"
    verbose_name = "Displays"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "displays"
    nora_title = "Displays"
    nora_description = ("The always-on 24\" wall screen and the 10.1\" kiosk that "
                        "drives it.")
    nora_icon = "monitor"
    nora_category = Category.HOUSE
    nora_order = 15
    nora_url_prefix = "home/displays/"
    # No nav entry: the screens' status cards live on the Settings page, next
    # to the wall power schedule that configures them. /home/displays/
    # redirects there. The wall and kiosk pages themselves are unaffected —
    # they are what the two physical screens actually load.
    nora_nav = False
