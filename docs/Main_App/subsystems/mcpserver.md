# MCP server — `nora_home.mcpserver`

## What it is

The house, exposed to AI agents as MCP tools. Any app can publish a tool; agents
with the right scope can call it.

This is one of exactly **two** touchpoints between Nora Home and Nora the robot: the
robot may read the MCP tools with a scoped device token. (The other is
`POST /api/homebot/say/`.) See [`../architecture.md`](../architecture.md) §
Boundaries.

## Status

**Built, unproven.** Never exercised by a real MCP client.

## Models

None of its own. Authentication uses `core.models.DeviceToken`, which carries the
scopes.

## Transports

| Transport | How |
|---|---|
| stdio | `manage.py mcp_stdio` — for a local agent |
| HTTP | `/mcp/tools/` and `/mcp/call/` |

Both require a **device token**, not a session. That is why this app sets
`nora_has_page = False`: a human clicking through from the Apps page would get a
bare `{"error": "unauthorized"}`, not a page, so it does not belong in a directory
of things a person can visit.

## Publishing a tool

Set `nora_provides_mcp_tools = True` in your `apps.py`, put tools in `mcp_tools.py`,
and import it from `ready()` so the decorator runs.

```python
@mcp_tool(
    name="workout_week",
    description="Sets, reps and volume for the current week.",
    schema={"type": "object", "properties": {...}},
    scopes=["read"],        # read | write | admin
    app_slug="workout",
    dangerous=False,        # True = agent must confirm explicitly
)
def workout_week(...): ...
```

Scopes are enforced per token, so the robot can be given read-only access to the
house without being able to change anything.

## What it offers other apps

`mcp_tool` (the decorator), `all_tools()`, `get_tool()`, `tools_for_scopes()`. See
[`../cross-functionality.md`](../cross-functionality.md#mcp).

## Background work

None.

## Settings

| Key | For |
|---|---|
| `NORA_HOME_MCP_ENABLED` | Master switch |
| `NORA_HOME_MCP_TOKEN` | Bootstrap token |

`nora_minimum_role = "admin"`.

## Known gaps

- Never called by a real MCP client — no agent has connected.
- No tests (Story 21).

## Files

```
registry.py   mcp_tool decorator, MCPTool, scope filtering
tools.py      the platform's own tools
views.py      list_tools (GET), call_tool (POST)
management/commands/mcp_stdio.py
```
