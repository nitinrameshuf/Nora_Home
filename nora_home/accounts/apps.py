from nora_home.core.registry import Category, NoraAppConfig


class AccountsConfig(NoraAppConfig):
    name = "nora_home.accounts"
    label = "accounts"
    verbose_name = "Household"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "household"
    nora_title = "Household"
    nora_description = "Who lives here, their roles, and how to reach each of them."
    nora_icon = "users"
    nora_category = Category.SYSTEM
    nora_nav = False
    # accounts/ itself has no index route (only switch/, me/, household/,
    # logout/) — household/ is the one that's actually a real, working page.
    nora_url_prefix = "accounts/household/"
    nora_order = 10
