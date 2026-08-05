from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from houseapps.example_habit.models import Habit
from nora_home.core.audit import record
from nora_home.tracker.api import complete_source, history_for, open_items_for


@login_required
def index(request):
    """Everything this person is trying to keep up."""
    habits = Habit.objects.filter(owner=request.user, is_active=True)
    open_today = {
        occurrence.trackable.source_ref: occurrence
        for occurrence in open_items_for(request.user)
        if occurrence.trackable.app_slug == "habits"
    }
    return render(request, "example_habit/index.html", {
        "habits": habits,
        "open_today": open_today,
        "page_title": "Habits",
    })


@login_required
def detail(request, uuid):
    habit = get_object_or_404(Habit, uuid=uuid, owner=request.user)
    occurrences = history_for(app_slug="habits", source_ref=str(habit.pk))
    return render(request, "example_habit/detail.html", {
        "habit": habit,
        "occurrences": occurrences,
        "page_title": habit.title,
    })


@login_required
@require_POST
def mark_done(request, uuid):
    """Complete today's occurrence.

    Going through `complete_source` rather than writing our own "done" flag is what
    keeps streaks, escalation, and the wall display consistent — the platform stops
    nagging because it knows, not because we told it separately.
    """
    habit = get_object_or_404(Habit, uuid=uuid, owner=request.user)
    completion = complete_source(
        app_slug="habits", source_ref=str(habit.pk), member=request.user,
        note=request.POST.get("note", "")[:500],
    )
    if completion is None:
        return JsonResponse({"ok": False, "error": "Nothing open for this one today."},
                            status=400)

    record("habits", "habit.completed", actor=request.user, subject=habit.title)
    return JsonResponse({"ok": True})
