from nora_home.core.registry import Category, NoraAppConfig


class MCPServerConfig(NoraAppConfig):
    name = "nora_home.mcpserver"
    label = "mcpserver"
    verbose_name = "MCP Server"

    # Level 1 — the base platform. See nora_home.core.registry.NoraAppConfig.
    nora_level = 1

    nora_slug = "mcp"
    nora_title = "MCP"
    nora_description = "Exposes the house to AI agents as MCP tools."
    nora_icon = "plug"
    nora_category = Category.SYSTEM
    nora_nav = False
    nora_order = 40
    nora_url_prefix = "mcp/"
    nora_minimum_role = "admin"
    # Real endpoints (mcp/tools/, mcp/call/), but both require MCP device-
    # token auth, not the regular session login every other directory entry
    # assumes — a human admin clicking through would just get a 401 JSON
    # body, not a page. Machine-only, so it doesn't belong in a directory of
    # things a person can visit.
    nora_has_page = False

    def ready(self):
        # Importing the module registers the platform's own tools.
        from nora_home.mcpserver import tools  # noqa: F401
