"""Dashboard, app directory, the House log, settings, health, and error pages."""

from __future__ import annotations

from datetime import timedelta

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from nora_home.core.audit import record
from nora_home.core.health import collect_health
from nora_home.core.registry import house_apps

WALL_SCHEDULE_KEY = "displays.wall_power_schedule"
WALL_SCHEDULE_DEFAULT = {"enabled": False, "start_hour": 9, "end_hour": 20}


@login_required
def app_directory(request):
    """Apps the family has added to the house — not the platform's own
    built-in pieces (Displays, Alerts, Todo, and so on are each their own
    Django app internally, for code organization, but nobody "installed"
    them the way a family app gets added; house_apps() is the registry's own
    name for that distinction). Empty until someone adds one.

    Also filters to nora_has_page=True: a couple of platform apps exist
    purely to hold registry metadata (widget ownership, telemetry
    provenance) with no urls.py and no page of their own — showing those
    meant rows pointing at a URL that either 404s or silently lands on a
    completely different app's page. This mostly matters if a future house
    app ever does the same.
    """
    return render(request, "core/app_directory.html", {
        "apps": [a for a in house_apps(include_disabled=True) if a.has_page],
        "page_title": "Apps",
    })


@never_cache
def health(request):
    """Machine-readable vitals. Used by the kiosk, systemd, and uptime checks.

    Deliberately unauthenticated: it exposes service up/down and resource
    percentages only, and something has to be able to check the house while nobody
    is logged in.
    """
    report = collect_health()
    return JsonResponse(report, status=200 if report["healthy"] else 503)


@never_cache
def weather_current(request):
    """Season / time-of-day / weather for the living background. Polled every
    few minutes by nh-scene.js on the wall and kiosk, which otherwise sit open
    for hours and would never see a change without this.

    Deliberately unauthenticated, same reasoning as health(): the wall and
    kiosk are never logged in as anyone in particular.
    """
    from nora_home.ui.scene import current_scene

    return JsonResponse(current_scene())


@login_required
def system_status(request):
    """Human-readable version of /health, plus recent audit activity."""
    from nora_home.core.models import AuditEvent

    return render(request, "core/system_status.html", {
        "health": collect_health(),
        "events": AuditEvent.objects.select_related("actor")[:50],
        "version": settings.NORA_HOME_VERSION,
        "environment": settings.NORA_HOME_ENV,
        "page_title": "System",
    })


@login_required
def house_log(request):
    """The House log — every subsystem's record of itself, on one timeline.

    All filtering is in the query string and nothing is stored, so a filtered
    view is a URL someone can send to somebody else. See nora_home.core.houselog
    for what counts as an event and why most of what the house does does not.
    """
    from nora_home.core import houselog

    days = _clamp_int(request.GET.get("days"), houselog.DEFAULT_DAYS, 1, 365)
    since = timezone.now() - timedelta(days=days)
    chosen = [s for s in request.GET.getlist("source") if s in houselog.SOURCES]
    severity = request.GET.get("severity", "")
    query = request.GET.get("q", "").strip()

    entries = houselog.timeline(since=since, sources=chosen or None,
                                severity=severity, query=query)

    return render(request, "core/house_log.html", {
        "entries": entries,
        "charts": houselog.charts(entries, since=since, until=timezone.now()),
        "sources": houselog.SOURCES,
        "chosen_sources": chosen,
        "severities": houselog.SEVERITY_ORDER,
        "severity": severity,
        "days": days,
        "q": query,
        # The cap is worth saying out loud rather than letting the page quietly
        # end: "200 entries" and "200 entries, and there were more" are different
        # answers to "did anything else happen".
        "truncated": len(entries) >= houselog.DEFAULT_LIMIT,
        "limit": houselog.DEFAULT_LIMIT,
        "page_title": "House log",
    })


def _clamp_int(raw, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(raw), high))
    except (TypeError, ValueError):
        return default


@login_required
@require_http_methods(["GET", "POST"])
def settings_page(request):
    """House-wide configuration plus this member's own profile — merged onto
    one page so the nav doesn't need a separate "You" entry. House settings
    started as one setting (the wall schedule), backed by a HouseSetting row
    rather than a new model, until there are enough to justify a registry of
    their own; the profile half is what used to be accounts:profile.
    """
    from nora_home.core.settings_store import get_setting, set_setting

    if request.method == "POST":
        schedule = {
            "enabled": request.POST.get("wall_schedule_enabled") == "on",
            "start_hour": _clamp_hour(request.POST.get("wall_schedule_start"), 9),
            "end_hour": _clamp_hour(request.POST.get("wall_schedule_end"), 20),
        }
        set_setting(
            WALL_SCHEDULE_KEY,
            schedule,
            app_slug="displays",
            description="When the 24\" wall display powers off overnight/off-hours.",
        )
        # The new value goes in the audit row, not just the fact of a change:
        # "why did the wall go dark at six" is answerable from the log only if
        # the log says what the hours were set to, and by whom.
        record("core", "setting.changed", actor=request.user,
               subject="Wall display schedule", key=WALL_SCHEDULE_KEY, **schedule)
        return redirect(reverse("core:settings"))

    from nora_home.displays.models import Display

    wall_schedule = get_setting(WALL_SCHEDULE_KEY, default=WALL_SCHEDULE_DEFAULT)
    return render(request, "core/settings.html", {
        "wall_schedule": wall_schedule,
        "member": request.user,
        "chain": request.user.escalation_chain(),
        # The two physical screens. Imported inside the view rather than at
        # module level: core must not depend on another app at import time.
        "displays": Display.objects.filter(is_active=True),
        "page_title": "Settings",
    })


def _clamp_hour(raw, default: int) -> int:
    return _clamp_int(raw, default, 0, 23)


def not_found(request, exception=None):  # noqa: ARG001
    return render(request, "core/404.html", status=404)


def server_error(request):
    return render(request, "core/500.html", status=500)
