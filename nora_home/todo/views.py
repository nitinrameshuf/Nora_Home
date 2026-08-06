"""
The board and its actions. See docs/Main_App/subsystems/todo.md §6 for the
surface design, and §4/§4a for the rules these views enforce through
nora_home.todo.api rather than re-deriving them here.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Count, Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from nora_home.core.audit import record
from nora_home.core.registry import scope_members
from nora_home.todo import analytics, api, tone
from nora_home.todo.calendar import events_by_day, month_weeks, shift_month
from nora_home.todo.forms import TaskForm
from nora_home.todo.reminders import ensure_default_reminder
from nora_home.todo.search import FilterParams, search_tasks
from nora_home.todo.models import (
    Event,
    Instance,
    InstanceOutcome,
    Label,
    Priority,
    SavedFilter,
    Task,
    TaskSource,
    TaskState,
    TodoPreference,
    Tone,
)
from nora_home.todo.scheduling import materialize


@login_required
def board(request):
    """Priority 1 · 2 · 3 · Archived, each with a live count. No Inbox, no
    Today, no Upcoming (§6) — a card sits in the column its priority puts it
    in, and stays there until someone edits it.
    """
    context = _board_context(request, source=TaskSource.USER)
    context["page_title"] = "Due today" if context["due_today"] else "Tasks"
    return render(request, "todo/board.html", context)


@login_required
def system_board(request):
    """§8: Nora Home's own tasks, filtered to `source=system` — "the same
    board, same shape." A telemetry threshold breach or a repeatedly-failing
    integration lands here (nora_home.todo.system_tasks); nothing else creates
    one, so there is no create button and no label toolbar to manage."""
    context = _board_context(request, source=TaskSource.SYSTEM)
    context["page_title"] = "System"
    context["is_system"] = True
    return render(request, "todo/board.html", context)


def _board_context(request, *, source: str) -> dict:
    members = scope_members(request)
    tasks = (api.tasks_for(members, queryset=Task.objects.alive().filter(source=source))
             .exclude(state=TaskState.DONE)
             .prefetch_related("assignees", "labels")
             .select_related("owner", "approver"))

    label_slug = request.GET.get("label", "")
    if label_slug:
        tasks = tasks.filter(labels__name=label_slug)

    # `?due=today` — the kiosk's "Due today" tile lands here rather than on a
    # separate page, for the same reason the board itself is one view: one
    # place to keep the priority-column and awaiting-approval logic correct.
    due_today = request.GET.get("due") == "today"
    if due_today:
        today = timezone.localdate()
        tasks = tasks.filter(
            instances__outcome__in=[InstanceOutcome.PENDING, InstanceOutcome.AWAITING_APPROVAL],
            instances__due_at__date=today,
        ).distinct()

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

    return {
        "columns": [(p, Priority(p).label, columns[p]) for p in Priority.values],
        "archived": archived,
        "awaiting": awaiting,
        "labels": Label.objects.all(),
        "active_label": label_slug,
        "due_today": due_today,
        "is_system": False,
        "nh_view_scope": request.session.get("nh_view_scope", "self"),
        "now": timezone.now(),
    }


@login_required
def calendar_view(request):
    """Month view only (§6). Events plus task instances, planned and actual
    in distinguishable weights, on a hand-written CSS grid.
    """
    today = timezone.localdate()
    try:
        year = int(request.GET.get("year", today.year))
        month = int(request.GET.get("month", today.month))
        date(year, month, 1)  # raises for an out-of-range month/year
    except (TypeError, ValueError):
        year, month = today.year, today.month

    weeks = month_weeks(year, month)
    range_start, range_end = weeks[0][0], weeks[-1][-1]

    members = scope_members(request)
    # Archived tasks go quiet everywhere else (§4) — the calendar is no
    # exception. A one-shot task's DONE state is not excluded: its instance is
    # real history and belongs on the day it actually happened.
    tasks = api.tasks_for(members, queryset=Task.objects.alive().exclude(state=TaskState.ARCHIVED))
    instances = (Instance.objects
                 .filter(due_at__date__gte=range_start, due_at__date__lte=range_end,
                        task__in=tasks)
                 .select_related("task")
                 .order_by("due_at"))

    planned = defaultdict(list)
    actual = defaultdict(list)
    for instance in instances:
        day = timezone.localtime(instance.due_at).date()
        bucket = planned if instance.outcome == InstanceOutcome.PENDING else actual
        bucket[day].append(instance)

    member_ids = [m.pk for m in members]
    events = Event.objects.alive().filter(Q(owner__isnull=True) | Q(owner_id__in=member_ids))
    days_flat = [day for week in weeks for day in week]
    events_on = events_by_day(events, days_flat)

    grid = [
        [{
            "date": day, "in_month": day.month == month, "is_today": day == today,
            "planned": planned.get(day, []), "actual": actual.get(day, []),
            "events": events_on.get(day, []),
        } for day in week]
        for week in weeks
    ]

    prev_year, prev_month = shift_month(year, month, -1)
    next_year, next_month = shift_month(year, month, 1)

    return render(request, "todo/calendar.html", {
        "grid": grid,
        "month_label": date(year, month, 1).strftime("%B %Y"),
        "prev_url": f"?year={prev_year}&month={prev_month}",
        "next_url": f"?year={next_year}&month={next_month}",
        "on_current_month": year == today.year and month == today.month,
        "page_title": "Calendar",
    })


@login_required
def search(request):
    """Full text plus combinable filters (§7). Empty on first load rather
    than mirroring the board — Search is a distinct destination, not a second
    view of "my open tasks."""
    params = FilterParams.from_dict(request.GET.dict())
    members = scope_members(request)
    tasks = api.tasks_for(members, queryset=Task.objects.alive())

    results = (search_tasks(tasks, params)
              .select_related("owner").prefetch_related("labels", "assignees")
              if not params.is_empty() else Task.objects.none())

    return render(request, "todo/search.html", {
        "params": params,
        "results": results,
        "priorities": Priority.choices,
        "states": TaskState.choices,
        "house_members": _house_members(),
        "labels": Label.objects.all(),
        "saved_filters": SavedFilter.objects.filter(owner=request.user),
        "page_title": "Search",
    })


@login_required
@require_POST
def save_filter(request):
    params = FilterParams.from_dict(request.POST.dict())
    name = (request.POST.get("name") or "").strip()
    if not name or params.is_empty():
        return _respond(request, redirect_to="todo:search",
                        payload={"ok": False, "error": "Give the search a name and at least one filter."})

    SavedFilter.objects.update_or_create(
        owner=request.user, name=name, defaults={"params": params.as_dict()})
    record("todo", "search.saved", actor=request.user, subject=name)
    if _is_fetch(request):
        return JsonResponse({"ok": True})
    # Redirect back to the search that was just saved, not a bare results-less
    # page — the querystring is what makes "saved and returned to" true the
    # moment you save it, not only the next time you click it.
    return redirect(f"{reverse('todo:search')}?{urlencode(params.as_dict())}")


@login_required
@require_POST
def delete_saved_filter(request, pk):
    SavedFilter.objects.filter(owner=request.user, pk=pk).delete()
    return _respond(request, redirect_to="todo:search")


@login_required
def labels_view(request):
    """Every label, with a live count (§6). Counts exclude archived and
    deleted tasks — the same "not now means quiet" reasoning the calendar and
    reminders already apply, so a label's count matches what selecting it on
    the board would actually show."""
    labels = Label.objects.annotate(
        task_count=Count("tasks", filter=Q(tasks__deleted_at__isnull=True)
                         & ~Q(tasks__state=TaskState.ARCHIVED))
    )

    if request.method == "POST":
        name = (request.POST.get("name") or "").strip()
        colour = (request.POST.get("colour") or "").strip()
        if name:
            Label.objects.get_or_create(name=name, defaults={"colour": colour})
            record("todo", "label.created", actor=request.user, subject=name)
        return redirect("todo:labels")

    return render(request, "todo/labels.html", {
        "labels": labels,
        "page_title": "Labels",
    })


@login_required
def settings_view(request):
    """Todo's own settings, at /todo/settings/ — **not** the platform Settings
    page, which stays for base-app concerns (§4)."""
    preference, _ = TodoPreference.objects.get_or_create(member=request.user)

    if request.method == "POST":
        chosen = request.POST.get("tone")
        if chosen in dict(Tone.choices):
            preference.tone = chosen

        hour = _as_int(request.POST.get("default_due_hour"))
        if hour is not None and 0 <= hour <= 23:
            preference.default_due_hour = hour

        # Per-setting overrides sit *under* the preset (§10). Only values the
        # preset system knows are stored; anything else is dropped here rather
        # than being written and ignored later, so the row stays readable.
        overrides = {}
        for key, allowed in tone.SETTINGS.items():
            raw = request.POST.get(f"override_{key}")
            if raw in (None, "", "preset"):
                continue
            for value in allowed:
                if str(value) == raw:
                    overrides[key] = value
                    break
        preference.tone_overrides = overrides
        preference.save()
        record("todo", "settings.saved", actor=request.user, subject=preference.tone)
        return redirect("todo:settings")

    effective = tone.resolve(request.user)
    return render(request, "todo/settings.html", {
        "preference": preference,
        "hours": range(24),
        "tone_cards": _tone_cards(preference),
        "overrides": _override_rows(preference, effective),
        "page_title": "Todo settings",
    })


def _tone_cards(preference) -> list[dict]:
    """The three presets, each spelled out in full.

    Every preset shows *all* of its settings rather than only where it differs
    from Standard. §10's "nothing is withheld from anyone" is about the numbers,
    but the same courtesy applies to the choice itself: someone picking Calm
    should be able to read what they are getting without holding another card in
    their head to diff against.
    """
    return [{
        "value": value,
        "label": label,
        "chosen": preference.tone == value,
        "lines": [f"{tone.label_for(key)}: {tone.describe(key, setting)}"
                  for key, setting in tone.PRESETS[value].items()],
    } for value, label in Tone.choices]


def _override_rows(preference, effective) -> list[dict]:
    """One row per setting: "follow the preset", or a specific value pinned.

    The stored override is what selects the option, **not** the effective value
    — otherwise every setting would come back looking individually pinned to
    whatever the preset happened to say, and switching preset afterwards would
    appear to do nothing.
    """
    stored = preference.tone_overrides or {}
    # The *preset's* own value, with overrides deliberately not applied: the
    # "follow the preset" option has to say what the preset says, not echo back
    # whatever this person has already pinned on top of it.
    preset = tone.PRESETS.get(preference.tone, tone.PRESETS[Tone.STANDARD])
    rows = []
    for key, allowed in tone.SETTINGS.items():
        rows.append({
            "key": key,
            "label": tone.label_for(key),
            "following_preset": key not in stored,
            # `str(value)` is the wire format the POST branch above matches on;
            # the two must agree or an override silently never takes.
            "options": [{
                "raw": str(value),
                "label": tone.describe(key, value),
                "selected": key in stored and stored[key] == value,
            } for value in allowed],
            "preset_label": tone.describe(key, preset[key]),
            "effective_label": tone.describe(key, effective[key]),
        })
    return rows


@login_required
def reporting(request):
    """Todo's own visualization page (§10).

    Everything here comes from `nora_home.todo.analytics` — this view does no
    counting of its own, which is §13's rule and what keeps the page, the
    widgets and any future MCP tool agreeing on every number.

    Chart options are built here rather than in the template so the
    "empty is a sentence, never an axis" rule (§10, Visual discipline) is
    decided in one place, next to the data that knows whether it is empty.
    """
    members = scope_members(request)
    data = analytics.overview(members)
    settings = tone.resolve(request.user)

    return render(request, "todo/reporting.html", {
        "d": data,
        "tone": settings,
        "charts": _reporting_charts(data),
        "overdue_phrase": tone.describe_overdue(data["load"]["overdue"], settings)
                          if data["load"]["overdue"] else "",
        "red_overdue": tone.may_show_red("overdue", settings),
        "page_title": "Reporting",
    })


def _reporting_charts(d: dict) -> dict:
    """One ECharts option per chart, or `None` where there is nothing to draw.

    `None` is the signal the template renders as a sentence. Returning an
    empty series on real axes instead is exactly the failure §10 catalogues
    from the platform's own dashboard.
    """
    charts: dict = {}

    flow = d["flow"]
    charts["flow"] = {
        "xAxis": {"type": "category", "data": flow["days"],
                  "axisLabel": {"showMaxLabel": True}},
        "yAxis": {"type": "value", "name": "items"},
        "legend": {"data": ["Arrived", "Finished"]},
        "series": [
            {"name": "Arrived", "type": "line", "areaStyle": {},
             "showSymbol": False, "data": flow["arrived"]},
            {"name": "Finished", "type": "line", "areaStyle": {},
             "showSymbol": False, "data": flow["completed"]},
        ],
    } if flow["days"] else None

    histogram = d["histogram"]
    charts["histogram"] = {
        "xAxis": {"type": "category", "data": histogram["buckets"],
                  "name": "finished in a day"},
        "yAxis": {"type": "value", "name": "days"},
        "series": [{"type": "bar", "data": histogram["counts"]}],
    } if histogram["buckets"] else None

    heatmap = d["heatmap"]
    today = timezone.localdate()
    charts["heatmap"] = {
        "tooltip": {"trigger": "item"},
        "visualMap": {"min": 0, "max": max(c for _, c in heatmap) or 1,
                      "type": "piecewise", "orient": "horizontal",
                      "left": "center", "top": 0, "showLabel": False},
        # Not `today.replace(year=year - 1)`: that raises ValueError on 29
        # February, so the whole Reporting page would 500 one day every four
        # years. The heatmap window is "a year back", and 365 days is that.
        "calendar": {"range": [str(today - timedelta(days=365)), str(today)],
                     "cellSize": ["auto", 13], "top": 50,
                     "splitLine": {"show": False},
                     "itemStyle": {"borderWidth": 2},
                     "yearLabel": {"show": False}},
        "series": [{"type": "heatmap", "coordinateSystem": "calendar", "data": heatmap}],
    } if heatmap else None

    rhythm = d["rhythm"]
    charts["rhythm"] = {
        "xAxis": {"type": "category",
                  "data": [f"{h:02d}" for h in range(24)], "name": "hour"},
        "yAxis": {"type": "value", "name": "finished"},
        "series": [{"type": "bar", "data": rhythm["hours"]}],
    } if rhythm["total"] else None

    charts["weekdays"] = {
        "xAxis": {"type": "category",
                  "data": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]},
        "yAxis": {"type": "value", "name": "finished"},
        "series": [{"type": "bar", "data": rhythm["weekdays"]}],
    } if rhythm["total"] else None

    labels = d["labels"]
    charts["labels"] = {
        "tooltip": {"trigger": "item"},
        "series": [{
            "type": "pie", "radius": ["45%", "70%"],
            "itemStyle": {"borderWidth": 2},
            "label": {"formatter": "{b}: {c}"},
            "data": [{"name": row["label"] or "Unlabelled", "value": row["count"]}
                     for row in labels],
        }],
    } if labels else None

    aging = d["aging_columns"]
    buckets = ["< 1 week", "1–4 weeks", "1–3 months", "> 3 months"]
    has_aging = any(sum(row["buckets"].values()) for row in aging)
    charts["aging"] = {
        "xAxis": {"type": "category", "data": buckets},
        "yAxis": {"type": "value", "name": "open items"},
        "legend": {"data": [row["label"] for row in aging]},
        "series": [{"name": row["label"], "type": "bar", "stack": "age",
                    "data": [row["buckets"][b] for b in buckets]}
                   for row in aging],
    } if has_aging else None

    estimates = d["estimates"]
    charts["estimates"] = {
        "xAxis": {"type": "value", "name": "planned min"},
        "yAxis": {"type": "value", "name": "actual min"},
        "series": [{"type": "scatter", "symbolSize": 8,
                    "data": list(map(list, zip(estimates["planned"],
                                               estimates["actual"])))}],
    } if estimates["count"] else None

    return charts


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
        # Snapshot *before* the form touches the instance — ModelForm mutates
        # the object it was given, so reading due_on/priority after
        # `form.save(commit=False)` would compare a value against itself.
        before = api.snapshot(task)
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
                api.record_changes(task, before, actor=request.user)
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
    before = api.snapshot(task)
    task.state = TaskState.ARCHIVED
    task.save(update_fields=["state", "updated_at"])
    api.record_changes(task, before, actor=request.user)
    record("todo", "task.archived", actor=request.user, subject=task.title)
    return _respond(request, redirect_to="todo:board")


@login_required
@require_POST
def restore(request, uuid):
    task = get_object_or_404(Task.objects.alive(), uuid=uuid)
    before = api.snapshot(task)
    task.state = TaskState.OPEN
    task.save(update_fields=["state", "updated_at"])
    api.record_changes(task, before, actor=request.user)
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
