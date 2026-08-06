"""Platform MCP tools — what an agent can learn about the house out of the box."""

from __future__ import annotations

from django.utils import timezone

from nora_home.mcpserver.registry import mcp_tool


@mcp_tool(
    name="house_overview",
    description=(
        "The state of the whole house right now: who lives here, which apps are "
        "installed, how many items are open or overdue, and whether the system is "
        "healthy. Call this first when you need orientation before a more specific "
        "question."
    ),
    app_slug="core",
)
def house_overview(**_):
    from nora_home.accounts.models import HouseMember
    from nora_home.core.health import collect_health
    from nora_home.core.registry import registered_apps

    health = collect_health()
    open_items, overdue_items = _task_counts()
    return {
        "time": timezone.localtime().isoformat(),
        "healthy": health["healthy"],
        "degraded": health["degraded"],
        "members": [
            {"username": m.get_username(), "name": m.name, "role": m.role}
            for m in HouseMember.objects.filter(is_active=True)
        ],
        "apps": [
            {"slug": a.slug, "title": a.title, "category": a.category,
             "description": a.description}
            for a in registered_apps()
        ],
        "open_items": open_items,
        "overdue_items": overdue_items,
    }


def _task_counts() -> tuple[int | None, int | None]:
    """How much the house owes, or (None, None) if Todo is not installed.

    Todo is Level 2 — the base leans on it, but it is deliberately uninstallable
    (docs/Main_App/subsystems/todo.md §1). An orientation tool losing two numbers
    is a degraded answer; raising ImportError inside the first tool an agent
    calls is a cascade. `None` says "not measured here", which an agent can read;
    a `0` would be a lie.
    """
    try:
        from nora_home.todo.models import Instance, InstanceOutcome, TaskState
    except ImportError:
        return None, None

    open_instances = Instance.objects.filter(
        outcome=InstanceOutcome.PENDING,
        task__state=TaskState.OPEN,
        task__deleted_at__isnull=True,
    )
    return open_instances.count(), open_instances.filter(due_at__lt=timezone.now()).count()


@mcp_tool(
    name="recent_telemetry",
    description=(
        "Recent readings for a named measurement series — a robot sensor, a body "
        "weight, a room temperature, a stock price. Call this when the question "
        "concerns a number that changes over time. Use list_telemetry_series first "
        "if you do not know the series name."
    ),
    schema={
        "type": "object",
        "properties": {
            "series": {"type": "string", "description": "Series key, e.g. nora.battery."},
            "hours": {"type": "integer", "description": "Look-back in hours (default 24)."},
            "limit": {"type": "integer", "description": "Max points (default 100)."},
        },
        "required": ["series"],
    },
    app_slug="telemetry",
)
def recent_telemetry(series: str, hours: int = 24, limit: int = 100, **_):
    from nora_home.telemetry.models import Reading

    since = timezone.now() - timezone.timedelta(hours=int(hours))
    points = (Reading.objects.filter(series__key=series, recorded_at__gte=since)
              .order_by("-recorded_at")[: min(int(limit), 500)])
    return {
        "series": series,
        "points": [
            {"at": p.recorded_at.isoformat(), "value": p.value, "tags": p.tags}
            for p in points
        ],
    }


@mcp_tool(
    name="list_telemetry_series",
    description="Every measurement series the house records, with its unit and owner "
                "app. Call this to discover what data exists before querying it.",
    app_slug="telemetry",
)
def list_telemetry_series(**_):
    from nora_home.telemetry.models import Series

    return [
        {"key": s.key, "label": s.label, "unit": s.unit, "app": s.app_slug,
         "category": s.category, "latest": s.latest_value()}
        for s in Series.objects.filter(is_active=True)
    ]


@mcp_tool(
    name="send_house_alert",
    description=(
        "Send a notification to the household — Slack, the wall display, and the "
        "in-app inbox. Use only when you have something the family genuinely needs "
        "to see now; this interrupts real people."
    ),
    schema={
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "body": {"type": "string"},
            "severity": {"type": "string",
                         "enum": ["info", "nudge", "warning", "alert"]},
        },
        "required": ["title"],
    },
    scopes=["read", "write"],
    app_slug="notifications",
    dangerous=True,
)
def send_house_alert(title: str, body: str = "", severity: str = "info", **_):
    from nora_home.notifications.api import notify_house

    notification = notify_house(title=title, body=body, severity=severity,
                                app_slug="mcp")
    return {"sent": True, "notification_id": notification.pk}
