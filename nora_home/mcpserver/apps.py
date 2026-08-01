from nora_home.core.registry import Category, NoraAppConfig


class MCPServerConfig(NoraAppConfig):
    name = "nora_home.mcpserver"
    label = "mcpserver"
    verbose_name = "MCP Server"

    nora_slug = "mcp"
    nora_title = "MCP"
    nora_description = "Exposes the house to AI agents as MCP tools."
    nora_icon = "plug"
    nora_category = Category.SYSTEM
    nora_nav = False
    nora_order = 40
    nora_url_prefix = "mcp/"
    nora_minimum_role = "admin"

    def ready(self):
        # Importing the module registers the platform's own tools.
        from nora_home.mcpserver import tools  # noqa: F401
