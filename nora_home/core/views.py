"""Dashboard, System (health + the House log, merged in Story 47), settings,
health, and error pages."""

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

WALL_SCHEDULE_KEY = "displays.wall_power_schedule"
WALL_SCHEDULE_DEFAULT = {"enabled": False, "start_hour": 9, "end_hour": 20}


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
    """The System page — Story 47 merged what used to be Status and the House
    log. Health/install cards plus the log's own filterable timeline, on one
    page; "Recent activity" (an unfiltered AuditEvent list) is gone, since the
    timeline's own "audit" source already shows the same events, filterable
    alongside health/notification/integration/telemetry ones — see
    nora_home.core.houselog for what counts as an event and why most of what
    the house does does not.

    The filter form is a plain GET form on purpose — no JavaScript, no stored
    state. Every view of this page is a URL, so "look at what happened on
    Tuesday" is something one person can send another.
    """
    from nora_home.core import houselog

    days = _clamp_int(request.GET.get("days"), houselog.DEFAULT_DAYS, 1, 365)
    since = timezone.now() - timedelta(days=days)
    chosen = [s for s in request.GET.getlist("source") if s in houselog.SOURCES]
    severity = request.GET.get("severity", "")
    query = request.GET.get("q", "").strip()

    entries = houselog.timeline(since=since, sources=chosen or None,
                                severity=severity, query=query)

    health = collect_health()

    return render(request, "core/system_status.html", {
        "health": health,
        "health_summary": _health_summary(health["services"]),
        "version": settings.NORA_HOME_VERSION,
        "environment": settings.NORA_HOME_ENV,
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
        "page_title": "System",
    })


@login_required
def styleguide(request):
    """Every component in `nora_home/ui/templatetags/nh.py`, in every state —
    empty, loading, error, overflow (Story 45's own file list). Fixture data
    here is grounded the same way DEVELOPMENT.md asks the mockup to be:
    `registered_apps()` for the Picker demo (not an invented app list), and
    the exact dict shapes `StatWidget.stat()` / `ListWidget.rows()` actually
    return for Stat and List — so a caller can copy a card here and know it
    will render for real.

    Not linked from any nav yet; IA is Story 47's job. Reachable directly at
    /home/styleguide/ by any signed-in member — same as every other page in
    this house, nothing here is secret, it is just not wired in yet.
    """
    from nora_home.core.registry import registered_apps

    apps = [a for a in registered_apps() if a.nav][:5]
    picker_items = [{"slug": a.slug, "title": a.title} for a in apps]

    # Demo rows only — shaped exactly like ListWidget.rows()/StatWidget.stat()
    # so a card copied from here renders identically once fed real data.
    due_rows = [
        {"title": "Take the bins out", "meta": "2 days late", "status": "late", "url": "#"},
        {"title": "Change the water filter", "meta": "Tomorrow", "status": "", "url": "#"},
        {"title": "Book the boiler service", "meta": "Sat 16", "status": "", "url": "#"},
    ]
    overflow_rows = [
        {"title": f"Task {n}", "meta": "Wed", "status": "", "url": "#"} for n in range(1, 11)
    ]

    return render(request, "core/styleguide.html", {
        "picker_items": picker_items,
        "due_rows": due_rows,
        "empty_rows": [],
        "overflow_rows": overflow_rows,
        "temp_spark": [48, 50, 49, 51, 53, 52, 54, 52],
        "chart_option": {
            "xAxis": {"type": "category", "data": ["Mon", "Tue", "Wed", "Thu", "Fri"]},
            "yAxis": {"type": "value"},
            "series": [{"type": "bar", "data": [1, 3, 2, 4, 3]}],
        },
        "page_title": "Styleguide",
    })


@login_required
def house_log(request):
    """Retired 2026-08-09 (Story 47) — System absorbed this page. Kept as a
    redirect, query string intact, so an old bookmark of a filtered log view
    (a URL someone was sent, per the docstring this page used to carry) still
    lands somewhere useful rather than 404ing. @login_required stays so an
    unauthenticated hit goes straight to the login page rather than bouncing
    through system/ first."""
    qs = request.META.get("QUERY_STRING", "")
    url = reverse("core:system_status")
    return redirect(f"{url}?{qs}" if qs else url)


def _clamp_int(raw, default: int, low: int, high: int) -> int:
    try:
        return max(low, min(int(raw), high))
    except (TypeError, ValueError):
        return default


# The order a person should read them in: what's fine first, what to worry
# about last. Anything collect_health() ever returns that isn't in here
# (there shouldn't be one) sorts after all of these rather than vanishing.
_HEALTH_STATUS_ORDER = ["ok", "warning", "skipped", "unknown", "down", "critical"]


def _health_summary(services: dict) -> list[dict]:
    """"3 ok · 1 skipped · 2 down" — collect_health() already returns every
    probe's real status (ok/down/skipped/warning/critical/unknown), including
    the honest "skipped" state for anything not enabled on this house. The
    System page used to only ever show a single healthy/degraded badge at the
    top; this is the count behind it, in the same wording as each row below."""
    counts: dict[str, int] = {}
    for probe in services.values():
        status = probe.get("status", "unknown")
        counts[status] = counts.get(status, 0) + 1

    ordered = sorted(counts.items(),
                     key=lambda item: (_HEALTH_STATUS_ORDER.index(item[0])
                                       if item[0] in _HEALTH_STATUS_ORDER else 99))
    return [{"status": status, "count": count} for status, count in ordered]


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

    from nora_home.ui import zoom as zoom_settings

    if request.method == "POST" and request.POST.get("form") == "zoom":
        # Its own form: saving a zoom must not also rewrite the power schedule,
        # and a page with two independent forms needs to know which one posted.
        zoom_settings.save(
            {"wall": request.POST.get("zoom_wall"),
             "kiosk": request.POST.get("zoom_kiosk")},
            actor=request.user,
        )
        return redirect(reverse("core:settings"))

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
        "zoom": zoom_settings.stored(),
        "zoom_min": zoom_settings.MIN_ZOOM,
        "zoom_max_wall": zoom_settings.MAX_ZOOM["wall"],
        "zoom_max_kiosk": zoom_settings.MAX_ZOOM["kiosk"],
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
