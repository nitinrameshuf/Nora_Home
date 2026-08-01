from nora_home.core.registry import Category, NoraAppConfig


class AccountsConfig(NoraAppConfig):
    name = "nora_home.accounts"
    label = "accounts"
    verbose_name = "Household"

    nora_slug = "household"
    nora_title = "Household"
    nora_description = "Who lives here, their roles, and how to reach each of them."
    nora_icon = "users"
    nora_category = Category.SYSTEM
    nora_nav = False
    nora_url_prefix = "accounts/"
    nora_order = 10
