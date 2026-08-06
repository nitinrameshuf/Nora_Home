"""
The board and its actions. See docs/Main_App/subsystems/todo.md §6 for the
surface design, and §4/§4a for the rules these views enforce through
nora_home.todo.api rather than re-deriving them here.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from nora_home.core.audit import record
from nora_home.core.registry import scope_members
from nora_home.todo import api
from nora_home.todo.forms import TaskForm
from nora_home.todo.reminders import ensure_default_reminder
from nora_home.todo.models import (
    Instance,
    InstanceOutcome,
    Label,
    Priority,
    Task,
    TaskSource,
    TaskState,
)
from nora_home.todo.scheduling import materialize


@login_required
def board(request):
    """Priority 1 · 2 · 3 · Archived, each with a live count. No Inbox, no
    Today, no Upcoming (§6) — a card sits in the column its priority puts it
    in, and stays there until someone edits it.
    """
    members = scope_members(request)
    tasks = (api.tasks_for(members, queryset=Task.objects.alive().filter(
                source=TaskSource.USER))
             .exclude(state=TaskState.DONE)
             .prefetch_related("assignees", "labels")
             .select_related("owner", "approver"))

    label_slug = request.GET.get("label", "")
    if label_slug:
        tasks = tasks.filter(labels__name=label_slug)

    current_by_task = {
        instance.task_id: instance
        for instance in Instance.objects.filter(
            task__in=tasks,
            outcome__in=[InstanceOutcome.PENDING, InstanceOutcome.AWAITING_APPROVAL],
        ).order_by("due_at")
    }

    # §4a: awaiting_approval "leaves the board's open columns (the work is
    # finished)". It still needs somewhere to be seen and acted on, so it gets
    # its own strip above the columns rather than sitting in a priority column
    # it has, in the sense that matters, already left.
    columns = {p: [] for p in Priority.values}
    archived = []
    awaiting = []
    for task in tasks:
        task.current = current_by_task.get(task.pk)
        if task.current is not None and task.current.outcome == InstanceOutcome.AWAITING_APPROVAL:
            awaiting.append(task)
        elif task.state == TaskState.ARCHIVED:
            archived.append(task)
        else:
            columns[task.priority].append(task)

    return render(request, "todo/board.html", {
        "columns": [(p, Priority(p).label, columns[p]) for p in Priority.values],
        "archived": archived,
        "awaiting": awaiting,
        "labels": Label.objects.all(),
        "active_label": label_slug,
        "page_title": "Tasks",
        "nh_view_scope": request.session.get("nh_view_scope", "self"),
        "now": timezone.now(),
    })


@login_required
def create(request):
    if request.method == "POST":
        form = TaskForm(request.POST, house_members=_house_members())
        if form.is_valid():
            task = form.save(commit=False)
            task.owner = task.owner or request.user
            try:
                task.full_clean()
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                task.save()
                form.save_m2m()
                materialize(task)
                ensure_default_reminder(task)
                record("todo", "task.created", actor=request.user, subject=task.title)
                return redirect("todo:board")
    else:
        form = TaskForm(initial={"owner": request.user},
                        house_members=_house_members())
    return render(request, "todo/form.html", {
        "form": form, "page_title": "New task", "is_new": True,
    })


@login_required
def detail(request, uuid):
    task = get_object_or_404(Task.objects.alive(), uuid=uuid)
    active = [InstanceOutcome.PENDING, InstanceOutcome.AWAITING_APPROVAL]
    return render(request, "todo/detail.html", {
        "task": task,
        "current": task.instances.filter(outcome__in=active).order_by("due_at").first(),
        "history": task.instances.exclude(outcome__in=active).order_by("-due_at")[:40],
        "comments": task.comments.select_related("author"),
        "attachments": task.attachments.all(),
        "links": task.links.all(),
        "approval_trail": task.changes.filter(field=api.APPROVAL).select_related("actor"),
        "page_title": task.title,
    })


@login_required
def edit(request, uuid):
    task = get_object_or_404(Task.objects.alive(), uuid=uuid)
    if request.method == "POST":
        form = TaskForm(request.POST, instance=task, house_members=_house_members())
        if form.is_valid():
            task = form.save(commit=False)
            try:
                task.full_clean()
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                task.save()
                form.save_m2m()
                materialize(task)
                ensure_default_reminder(task)
                record("todo", "task.edited", actor=request.user, subject=task.title)
                return redirect("todo:detail", uuid=task.uuid)
    else:
        form = TaskForm(instance=task, house_members=_house_members())
    return render(request, "todo/form.html", {
        "form": form, "task": task, "page_title": f"Edit {task.title}", "is_new": False,
    })


@login_required
@require_POST
def archive(request, uuid):
    """"Not now" — a real column, not a deletion. Priority is kept so restoring
    puts the task back where it was (§4)."""
    task = get_object_or_404(Task.objects.alive(), uuid=uuid)
    task.state = TaskState.ARCHIVED
    task.save(update_fields=["state", "updated_at"])
    record("todo", "task.archived", actor=request.user, subject=task.title)
    return _respond(request, redirect_to="todo:board")


@login_required
@require_POST
def restore(request, uuid):
    task = get_object_or_404(Task.objects.alive(), uuid=uuid)
    task.state = TaskState.OPEN
    task.save(update_fields=["state", "updated_at"])
    record("todo", "task.restored", actor=request.user, subject=task.title)
    return _respond(request, redirect_to="todo:board")


@login_required
@require_POST
def delete(request, uuid):
    """Anyone can create a task for anyone; anyone can delete one (§4) — there
    is no approval or ownership gate on this, deliberately."""
    task = get_object_or_404(Task.objects.alive(), uuid=uuid)
    task.delete()
    record("todo", "task.deleted", actor=request.user, subject=task.title)
    return _respond(request, redirect_to="todo:board")


@login_required
@require_POST
def complete(request, uuid):
    instance = get_object_or_404(Instance.objects.select_related("task"), uuid=uuid)
    try:
        instance = api.complete(
            instance, member=request.user,
            actual_minutes=_as_int(request.POST.get("actual_minutes")),
            note=request.POST.get("note") or None)
    except (PermissionDenied, ValidationError) as exc:
        return _error(request, exc, task=instance.task)
    record("todo", "instance.completed", actor=request.user, subject=instance.task.title)
    return _respond(request, redirect_to="todo:board",
                    payload={"ok": True, "outcome": instance.outcome})


@login_required
@require_POST
def uncomplete(request, uuid):
    instance = get_object_or_404(Instance.objects.select_related("task"), uuid=uuid)
    try:
        instance = api.uncomplete(instance, member=request.user)
    except (PermissionDenied, ValidationError) as exc:
        return _error(request, exc, task=instance.task)
    record("todo", "instance.uncompleted", actor=request.user, subject=instance.task.title)
    return _respond(request, redirect_to="todo:board")


@login_required
@require_POST
def skip(request, uuid):
    instance = get_object_or_404(Instance.objects.select_related("task"), uuid=uuid)
    try:
        instance = api.skip(instance, member=request.user,
                            reason=request.POST.get("reason", ""))
    except (PermissionDenied, ValidationError) as exc:
        return _error(request, exc, task=instance.task)
    record("todo", "instance.skipped", actor=request.user, subject=instance.task.title)
    return _respond(request, redirect_to="todo:board")


@login_required
@require_POST
def approve(request, uuid):
    instance = get_object_or_404(Instance.objects.select_related("task"), uuid=uuid)
    try:
        instance = api.approve(instance, member=request.user)
    except (PermissionDenied, ValidationError) as exc:
        return _error(request, exc, task=instance.task)
    record("todo", "instance.approved", actor=request.user, subject=instance.task.title)
    return _respond(request, redirect_to="todo:detail", redirect_kwargs={"uuid": instance.task.uuid})


@login_required
@require_POST
def reject(request, uuid):
    instance = get_object_or_404(Instance.objects.select_related("task"), uuid=uuid)
    try:
        instance = api.reject(instance, member=request.user,
                              reason=request.POST.get("reason", ""))
    except (PermissionDenied, ValidationError) as exc:
        return _error(request, exc, task=instance.task)
    record("todo", "instance.rejected", actor=request.user, subject=instance.task.title,
          reason=request.POST.get("reason", ""))
    return _respond(request, redirect_to="todo:detail", redirect_kwargs={"uuid": instance.task.uuid})


@login_required
@require_POST
def acknowledge(request, uuid):
    """"Seen it, will get to it" — stops the escalation ladder without
    claiming the work is done. No permission gate beyond being signed in:
    anyone the ladder reached (the owner, or someone widened in by a later
    rung) should be able to silence it."""
    instance = get_object_or_404(Instance.objects.select_related("task"), uuid=uuid)
    api.acknowledge(instance, member=request.user)
    record("todo", "instance.acknowledged", actor=request.user, subject=instance.task.title)
    return _respond(request, redirect_to="todo:detail", redirect_kwargs={"uuid": instance.task.uuid})


# ── helpers ──────────────────────────────────────────────────────────────────

def _is_fetch(request) -> bool:
    return request.headers.get("X-Requested-With") == "fetch"


def _respond(request, *, redirect_to: str, redirect_kwargs: dict | None = None,
            payload: dict | None = None):
    if _is_fetch(request):
        return JsonResponse(payload or {"ok": True})
    return redirect(redirect_to, **(redirect_kwargs or {}))


def _error(request, exc, *, task):
    message = exc.messages[0] if hasattr(exc, "messages") else str(exc)
    status = 403 if isinstance(exc, PermissionDenied) else 400
    if _is_fetch(request):
        return JsonResponse({"ok": False, "error": message}, status=status)
    from django.contrib import messages
    messages.error(request, message)
    return redirect("todo:detail", uuid=task.uuid)


def _house_members():
    from nora_home.accounts.models import HouseMember

    return HouseMember.objects.filter(is_active=True)


def _as_int(raw):
    try:
        return int(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None
