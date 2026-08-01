from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from nora_home.core.audit import record
from nora_home.tracker.models import Occurrence, Trackable
from nora_home.tracker.scheduling import materialize


@login_required
def board(request):
    """Everything open, grouped into overdue / today / ahead."""
    mine = Occurrence.objects.open().for_member(request.user).select_related("trackable")
    now = timezone.now()
    end_of_day = timezone.localtime(now).replace(hour=23, minute=59, second=59)
    return render(request, "tracker/board.html", {
        "overdue": mine.filter(due_at__lt=now).order_by("due_at"),
        "today": mine.filter(due_at__gte=now, due_at__lte=end_of_day).order_by("due_at"),
        "ahead": mine.filter(due_at__gt=end_of_day).order_by("due_at")[:30],
        "page_title": "Tracker",
    })


@login_required
def house_board(request):
    """Everyone's open items — the shared view the wall display mirrors."""
    items = (Occurrence.objects.open()
             .select_related("trackable", "trackable__owner")
             .order_by("due_at")[:200])
    by_member: dict = {}
    for occurrence in items:
        by_member.setdefault(occurrence.trackable.owner, []).append(occurrence)
    return render(request, "tracker/house_board.html", {
        "by_member": by_member,
        "page_title": "The house",
    })


@login_required
def trackable_detail(request, uuid):
    trackable = get_object_or_404(Trackable, uuid=uuid)
    return render(request, "tracker/detail.html", {
        "trackable": trackable,
        "occurrences": trackable.occurrences.select_related("completed_by")[:40],
        "streak": trackable.current_streak(),
        "page_title": trackable.title,
    })


@login_required
@require_POST
def complete(request, uuid):
    occurrence = get_object_or_404(
        Occurrence.objects.select_related("trackable"), uuid=uuid)
    occurrence.complete(
        member=request.user,
        note=request.POST.get("note", "")[:2000],
        value=_as_float(request.POST.get("value")),
    )
    materialize(occurrence.trackable)
    record("tracker", "occurrence.completed", actor=request.user,
           subject=occurrence.trackable.title, occurrence=str(occurrence.uuid))

    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"ok": True, "streak": occurrence.trackable.current_streak()})
    return redirect("tracker:board")


@login_required
@require_POST
def skip(request, uuid):
    occurrence = get_object_or_404(
        Occurrence.objects.select_related("trackable"), uuid=uuid)
    if not occurrence.trackable.allow_skip:
        return JsonResponse({"ok": False, "error": "This one can't be skipped."}, status=400)
    occurrence.skip(member=request.user, reason=request.POST.get("reason", "")[:500])
    materialize(occurrence.trackable)
    return JsonResponse({"ok": True})


@login_required
@require_POST
def acknowledge(request, uuid):
    occurrence = get_object_or_404(Occurrence, uuid=uuid)
    occurrence.acknowledge(request.user)
    record("tracker", "occurrence.acknowledged", actor=request.user,
           subject=str(occurrence), occurrence=str(occurrence.uuid))
    return JsonResponse({"ok": True})


def _as_float(raw):
    try:
        return float(raw) if raw not in (None, "") else None
    except (TypeError, ValueError):
        return None
