"""Dashboard, health, capabilities, and error pages."""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.cache import never_cache

from nora_home.core.health import collect_health
from nora_home.core.registry import registered_apps


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


def not_found(request, exception=None):  # noqa: ARG001
    return render(request, "core/404.html", status=404)


def server_error(request):
    return render(request, "core/500.html", status=500)
