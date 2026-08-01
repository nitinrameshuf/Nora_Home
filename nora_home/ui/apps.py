from nora_home.core.registry import Category, NoraAppConfig


class UIConfig(NoraAppConfig):
    name = "nora_home.ui"
    label = "ui"
    verbose_name = "Nora UI"

    nora_slug = "ui"
    nora_title = "Interface"
    nora_description = "The shell, the theme, the surfaces, and the home bot."
    nora_icon = "face"
    nora_category = Category.SYSTEM
    nora_nav = False
    nora_order = 1
    nora_url_prefix = "home/"
