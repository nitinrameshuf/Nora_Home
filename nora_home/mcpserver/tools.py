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
    from nora_home.tracker.models import Occurrence

    health = collect_health()
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
        "open_items": Occurrence.objects.open().count(),
        "overdue_items": Occurrence.objects.overdue().count(),
    }


@mcp_tool(
    name="open_items",
    description=(
        "Everything the house still owes, soonest first. Call this when asked what "
        "someone needs to do, what is late, or what is coming up. Filter by member "
        "username when the question is about one person."
    ),
    schema={
        "type": "object",
        "properties": {
            "member": {"type": "string", "description": "Username; omit for everyone."},
            "overdue_only": {"type": "boolean", "description": "Only late items."},
            "limit": {"type": "integer", "description": "Max rows (default 25)."},
        },
    },
    app_slug="tracker",
)
def open_items(member: str = "", overdue_only: bool = False, limit: int = 25, **_):
    from nora_home.tracker.models import Occurrence

    qs = Occurrence.objects.overdue() if overdue_only else Occurrence.objects.open()
    if member:
        qs = qs.filter(trackable__owner__username=member)
    qs = qs.select_related("trackable", "trackable__owner").order_by("due_at")

    return [
        {
            "id": str(o.uuid),
            "title": o.trackable.title,
            "owner": o.trackable.owner.get_username(),
            "app": o.trackable.app_slug,
            "due_at": o.due_at.isoformat(),
            "minutes_overdue": o.minutes_overdue,
            "escalation_level": o.escalation_level,
        }
        for o in qs[: min(int(limit), 100)]
    ]


@mcp_tool(
    name="member_reliability",
    description=(
        "How consistently a member completes what they take on, over a window of "
        "days. Use it when asked how someone is doing, or before deciding whether a "
        "goal is realistic for them."
    ),
    schema={
        "type": "object",
        "properties": {
            "member": {"type": "string", "description": "Username."},
            "days": {"type": "integer", "description": "Window in days (default 30)."},
        },
        "required": ["member"],
    },
    app_slug="tracker",
)
def member_reliability(member: str, days: int = 30, **_):
    from nora_home.tracker.models import Occurrence

    since = timezone.now() - timezone.timedelta(days=int(days))
    qs = Occurrence.objects.filter(trackable__owner__username=member, due_at__gte=since)
    done = qs.filter(status=Occurrence.Status.DONE).count()
    missed = qs.filter(status=Occurrence.Status.MISSED).count()
    total = done + missed
    return {
        "member": member,
        "window_days": days,
        "completed": done,
        "missed": missed,
        "completion_rate": round(done / total * 100, 1) if total else None,
        "still_open": qs.filter(status=Occurrence.Status.PENDING).count(),
    }


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
         "latest": s.latest_value()}
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
