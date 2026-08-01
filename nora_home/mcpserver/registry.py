"""
The house MCP tool registry.

Any app can publish a tool to agents — Claude Code, Claude Desktop, the Nora robot —
by decorating a plain function:

    from nora_home.mcpserver.registry import mcp_tool

    @mcp_tool(
        name="workout_week",
        description="Sets, reps, and volume for a member's current training week.",
        schema={
            "type": "object",
            "properties": {"member": {"type": "string", "description": "Username."}},
            "required": ["member"],
        },
        scopes=["read"],
    )
    def workout_week(member: str, **_):
        return {"sets": 42, "volume_kg": 8100}

The function receives validated-ish kwargs and returns anything JSON-serialisable.
Write tools are possible but must declare `scopes=["write"]`; the HTTP endpoint
refuses them unless the calling token carries that scope.

Describe *when* to call the tool, not just what it does — that is what makes an agent
reach for it at the right moment.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)

_REGISTRY: dict[str, "MCPTool"] = {}


@dataclass
class MCPTool:
    name: str
    description: str
    schema: dict
    handler: Callable
    scopes: list[str] = field(default_factory=lambda: ["read"])
    app_slug: str = ""
    dangerous: bool = False

    def as_definition(self) -> dict:
        """The shape an MCP client expects in a tools/list response."""
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": self.schema,
        }

    def call(self, arguments: dict):
        return self.handler(**arguments)


def mcp_tool(*, name: str, description: str, schema: dict | None = None,
             scopes: list[str] | None = None, app_slug: str = "",
             dangerous: bool = False):
    def decorator(func: Callable) -> Callable:
        if name in _REGISTRY:
            logger.warning("MCP tool %r is already registered; overwriting", name)
        _REGISTRY[name] = MCPTool(
            name=name,
            description=description,
            schema=schema or {"type": "object", "properties": {}},
            handler=func,
            scopes=scopes or ["read"],
            app_slug=app_slug,
            dangerous=dangerous,
        )
        return func

    return decorator


def all_tools() -> list[MCPTool]:
    return sorted(_REGISTRY.values(), key=lambda t: t.name)


def get_tool(name: str) -> MCPTool | None:
    return _REGISTRY.get(name)


def tools_for_scopes(scopes: list[str]) -> list[MCPTool]:
    granted = set(scopes)
    return [t for t in all_tools() if granted.issuperset(set(t.scopes))]
