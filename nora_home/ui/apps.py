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
    # No urls.py — this app exists only to hold registry metadata (theme,
    # surfaces, the home bot), not a page of its own. url_prefix would
    # otherwise be pure fiction on the Apps directory.
    nora_has_page = False
