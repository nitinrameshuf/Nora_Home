"""
Apps the family writes.

Anything in here is a house app: it plugs into the platform through
nora_home.core.registry and gets nav, dashboard cards, tracking, escalation,
notifications, AI, telemetry, and MCP for free. Always Level 3 (see
nora_home.core.registry.NoraAppConfig) — freely uninstallable, nothing above
this directory is ever allowed to depend on what's in it.

Start by reading docs/Main_App/DEVELOPMENT.md.
"""
