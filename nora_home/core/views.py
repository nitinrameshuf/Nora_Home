"""Dashboard, health, capabilities, and error pages."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from nora_home.core.health import collect_health
from nora_home.core.registry import registered_apps

WALL_SCHEDULE_KEY = "displays.wall_power_schedule"
WALL_SCHEDULE_DEFAULT = {"enabled": False, "start_hour": 9, "end_hour": 20}


@login_required
def app_directory(request):
    """Every app installed in the house, what it does, and who may see it."""
    return render(request, "core/app_directory.html", {
        "apps": registered_apps(include_disabled=True),
        "page_title": "Apps",
    })


def capabilities(request):
    """Serve docs/capabilities.html — the living record of what the platform does.

    Served from disk rather than duplicated into a template so that there is exactly
    one copy: editing the file updates this page, and the file is still openable on
    its own by anyone who has the repo.
    """
    path = settings.BASE_DIR / "docs" / "capabilities.html"
    if not path.exists():
        return render(request, "core/404.html", status=404)
    return HttpResponse(path.read_text(encoding="utf-8"))


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
@require_http_methods(["GET", "POST"])
def settings_page(request):
    """House-wide configuration. One setting today, more over time — each
    new one is a form field here backed by a HouseSetting row, not a new
    model, until there are enough to justify a registry of their own.
    """
    from nora_home.core.settings_store import get_setting, set_setting

    if request.method == "POST":
        set_setting(
            WALL_SCHEDULE_KEY,
            {
                "enabled": request.POST.get("wall_schedule_enabled") == "on",
                "start_hour": _clamp_hour(request.POST.get("wall_schedule_start"), 9),
                "end_hour": _clamp_hour(request.POST.get("wall_schedule_end"), 20),
            },
            app_slug="displays",
            description="When the 24\" wall display powers off overnight/off-hours.",
        )
        return redirect(reverse("core:settings"))

    wall_schedule = get_setting(WALL_SCHEDULE_KEY, default=WALL_SCHEDULE_DEFAULT)
    return render(request, "core/settings.html", {
        "wall_schedule": wall_schedule,
        "page_title": "Settings",
    })


def _clamp_hour(raw, default: int) -> int:
    try:
        return max(0, min(int(raw), 23))
    except (TypeError, ValueError):
        return default


def not_found(request, exception=None):  # noqa: ARG001
    return render(request, "core/404.html", status=404)


def server_error(request):
    return render(request, "core/500.html", status=500)
