from nora_home.core.registry import Category, NoraAppConfig


class AIConfig(NoraAppConfig):
    name = "nora_home.ai"
    label = "ai"
    verbose_name = "Nora AI"

    nora_slug = "ai"
    nora_title = "Assistant"
    nora_description = "Claude, wired into the house's own data."
    nora_icon = "spark"
    nora_category = Category.HOUSE
    nora_order = 30
    nora_url_prefix = "home/ai/"
