from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nora_home.telemetry.api import record_reading, series_history
from nora_home.telemetry.models import Series


@login_required
def index(request):
    """Retired 2026-08-10 (Story 55) — Measurements is a System tab now, not
    its own destination: the mockup's System page (SYS_VIEWS.measurements)
    never had a standalone one, only the four tabs. Kept as a redirect so an
    old bookmark or nav link still lands somewhere real."""
    return redirect(f"{reverse('core:system_status')}?tab=measurements")


@login_required
def detail(request, key):
    series = get_object_or_404(Series, key=key)
    return render(request, "telemetry/detail.html", {
        "series": series,
        "readings": series.readings.all()[:100],
        "latest": series.latest(),
        "page_title": series.label,
    })


@login_required
def history(request, key):
    """JSON for the chart on the detail page and the wall display."""
    hours = min(int(request.GET.get("hours", 24)), 24 * 90)
    points = series_history(key, hours=hours)
    return JsonResponse({
        "key": key,
        "points": [{"t": p.recorded_at.isoformat(), "v": p.value} for p in points],
    })


@login_required
@require_POST
def record(request, key):
    try:
        value = float(request.POST["value"])
    except (KeyError, TypeError, ValueError):
        return JsonResponse({"ok": False, "error": "value must be a number"}, status=400)

    reading = record_reading(key, value, member=request.user, source="manual")
    return JsonResponse({"ok": True, "value": reading.value,
                         "at": reading.recorded_at.isoformat()})
