"""
What an agent can ask about the house's tasks.

These two replace the tracker's `open_items` and `member_reliability`, deleted
with it in Story 40. Same tool names on purpose — an agent that already knows to
reach for `open_items` should keep working — but they answer from Todo's
Instance history rather than the tracker's Occurrences.

They live here rather than in `nora_home/mcpserver/tools.py` because they are
entirely task-domain: the platform should not have to know what a priority or an
assignee is in order to publish a tool about one.
"""

from __future__ import annotations

from django.db.models import Q
from django.utils import timezone

from nora_home.mcpserver.registry import mcp_tool
from nora_home.todo.models import Instance, InstanceOutcome, Priority, TaskState


def _open_instances():
    """Everything still genuinely owed.

    Archived and soft-deleted tasks are excluded at the query rather than
    filtered afterwards — "not now" is not the same as outstanding, and an agent
    told otherwise would go and chase somebody about it.
    """
    return (Instance.objects
            .filter(outcome=InstanceOutcome.PENDING,
                    task__state=TaskState.OPEN,
                    task__deleted_at__isnull=True)
            .select_related("task", "task__owner"))


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
    app_slug="todo",
)
def open_items(member: str = "", overdue_only: bool = False, limit: int = 25, **_):
    now = timezone.now()
    qs = _open_instances()
    if overdue_only:
        qs = qs.filter(due_at__lt=now)
    if member:
        # Owner *or* assignee: a shared task is on your plate either way, and an
        # agent asked "what does Priya need to do" that only matched `owner`
        # would silently omit every task she was assigned but does not own.
        # .distinct() because the assignee join multiplies rows — the same trap
        # documented on nora_home.todo.api.tasks_for().
        qs = qs.filter(
            Q(task__owner__username=member) | Q(task__assignees__username=member)
        ).distinct()

    return [
        {
            "id": str(i.uuid),
            "title": i.task.title,
            "owner": i.task.owner.get_username(),
            "priority": i.task.priority,
            "due_at": i.due_at.isoformat(),
            "minutes_overdue": max(0, int((now - i.due_at).total_seconds() // 60)),
            "escalation_level": i.escalation_level,
        }
        for i in qs.order_by("due_at")[: min(int(limit), 100)]
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
    app_slug="todo",
)
def member_reliability(member: str, days: int = 30, **_):
    since = timezone.now() - timezone.timedelta(days=int(days))
    qs = Instance.objects.filter(task__owner__username=member, due_at__gte=since,
                                 task__deleted_at__isnull=True)

    done = qs.filter(outcome=InstanceOutcome.DONE).count()
    missed = qs.filter(outcome=InstanceOutcome.MISSED).count()
    total = done + missed
    return {
        "member": member,
        "window_days": days,
        "completed": done,
        "missed": missed,
        # Skipped deliberately excluded from the denominator: a skip is a
        # decision, not a failure, and counting it as one would make a person who
        # keeps their board honest look worse than one who never touches it. The
        # same choice nora_home.todo.analytics makes.
        "skipped": qs.filter(outcome=InstanceOutcome.SKIPPED).count(),
        "completion_rate": round(done / total * 100, 1) if total else None,
        "still_open": qs.filter(outcome=InstanceOutcome.PENDING).count(),
        "awaiting_approval": qs.filter(
            outcome=InstanceOutcome.AWAITING_APPROVAL).count(),
        "overdue_p1": qs.filter(outcome=InstanceOutcome.PENDING,
                                due_at__lt=timezone.now(),
                                task__priority=Priority.P1).count(),
    }
