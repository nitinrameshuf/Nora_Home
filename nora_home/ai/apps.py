from nora_home.core.registry import Category, NoraAppConfig


class AIConfig(NoraAppConfig):
    name = "nora_home.ai"
    label = "ai"
    verbose_name = "Nora AI"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "ai"
    nora_title = "Assistant"
    nora_description = "Claude, wired into the house's own data."
    nora_icon = "spark"
    nora_category = Category.HOUSE
    nora_order = 30
    nora_url_prefix = "home/ai/"
    # Story 13 (dashboard) — built, never run against a real API key. Not
    # exposed as a live nav destination until that's actually proven; the
    # code, models, and console stay installed so proving it out later
    # doesn't mean building it from scratch.
    nora_nav = False
