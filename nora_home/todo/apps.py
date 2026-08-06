"""
Todo — the house's task system. Replaces the tracker (see
docs/Main_App/subsystems/todo.md); Level 2, not a house app.
"""

from nora_home.core.registry import Category, NoraAppConfig


class TodoConfig(NoraAppConfig):
    name = "nora_home.todo"
    label = "todo"
    verbose_name = "Todo"

    nora_slug = "todo"
    nora_title = "Todo"
    nora_description = "Everything that has to happen, when, and who hears about it."
    nora_icon = "check"
    nora_category = Category.SYSTEM
    # Level 2 — the base leans on this app (scheduling, reminders, escalation).
    # See docs/Main_App/subsystems/todo.md §1.
    nora_level = 2
    nora_order = 5
    nora_url_prefix = "todo/"

    # The board arrived in Phase 3 (Story 31). Still to come: nora_widgets
    # (Phase 7), nora_kiosk_controls (Phase 6), nora_provides_mcp_tools +
    # ready() importing mcp_tools (later).
    nora_has_page = True
    nora_nav = True
