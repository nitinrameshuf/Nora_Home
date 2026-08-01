"""
Run the house as a stdio MCP server, so Claude Desktop or Claude Code can use it.

    python manage.py mcp_stdio

Register it in your MCP client config:

    {
      "mcpServers": {
        "nora-home": {
          "command": "/srv/nora/.venv/bin/python",
          "args": ["/srv/nora/manage.py", "mcp_stdio"],
          "env": {"DJANGO_SETTINGS_MODULE": "config.settings.pi"}
        }
      }
    }

Every tool in nora_home.mcpserver.registry is exposed, including tools house apps added.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand

from nora_home.mcpserver.registry import all_tools, get_tool


class Command(BaseCommand):
    help = "Serve the house's MCP tools over stdio."

    def add_arguments(self, parser):
        parser.add_argument("--read-only", action="store_true",
                            help="Refuse tools that change house state.")

    def handle(self, *args, **options):
        try:
            from mcp.server.fastmcp import FastMCP
        except ImportError:
            raise SystemExit(
                "The `mcp` package is not installed. Run: pip install 'mcp>=1.2'"
            )

        read_only = options["read_only"]
        server = FastMCP("nora-home")

        for tool in all_tools():
            if read_only and "write" in tool.scopes:
                continue
            self._register(server, tool)

        server.run(transport="stdio")

    def _register(self, server, tool):
        """Bind one registry tool onto the FastMCP server.

        The handler is wrapped rather than passed directly so that a failing tool
        returns an error string the agent can read instead of killing the process.
        """

        def handler(arguments: str = "{}", _tool_name=tool.name) -> str:
            registered = get_tool(_tool_name)
            try:
                parsed = json.loads(arguments) if arguments else {}
            except json.JSONDecodeError:
                return "Error: `arguments` must be a JSON object."
            try:
                return json.dumps(registered.call(parsed), default=str, indent=2)
            except Exception as exc:  # surfaced to the agent, not raised
                return f"Error calling {_tool_name}: {exc}"

        handler.__name__ = tool.name
        handler.__doc__ = (
            f"{tool.description}\n\n"
            f"Pass `arguments` as a JSON object matching this schema:\n"
            f"{json.dumps(tool.schema, indent=2)}"
        )
        server.tool()(handler)
