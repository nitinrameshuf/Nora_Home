from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from nora_home.core.registry import navigation
from nora_home.displays.consumers import KIOSK_ACTIONS
from nora_home.displays.bus import send_to_display
from nora_home.displays.models import Display


@login_required
def wall(request, slug: str = ""):
    """The always-on 24" screen — a thin shell around an iframe of the real
    app. What it shows is driven remotely by the kiosk (see wall-live.js);
    this view just picks the starting page and registers the display row.
    """
    slug = slug or settings.NORA_HOME_MAIN_DISPLAY_SLUG
    display, _ = Display.objects.get_or_create(
        slug=slug, defaults={"name": slug.title(), "kind": Display.Kind.WALL})

    return render(request, "displays/wall_live.html", {
        "display": display,
        "default_path": reverse("core:dashboard"),
    })


@login_required
@xframe_options_sameorigin
def kiosk(request):
    """The 10.1" touchscreen. Big targets, one thumb — a remote control for
    the wall, never the app itself. Tiles mirror the same nav structure the
    sidebar uses, so a new house app appears here automatically. An app that
    declares nora_kiosk_controls (NoraAppConfig) gets its own button screen,
    swapped in on the kiosk the moment someone switches the wall to it.
    """
    role = getattr(request.user, "role", "member")
    nav = navigation(role)
    apps_with_controls = {
        app.slug: app
        for group in nav for app in group["apps"]
        if app.kiosk_controls
    }
    return render(request, "displays/kiosk.html", {
        "target": settings.NORA_HOME_MAIN_DISPLAY_SLUG,
        "nav": nav,
        "apps_with_controls": apps_with_controls,
        "home_url": reverse("core:dashboard"),
        "house_links": [
            {"title": "Apps", "url": reverse("core:app_directory")},
            {"title": "Status", "url": reverse("core:system_status")},
            {"title": "Settings", "url": reverse("core:settings")},
        ],
    })


@login_required
def manage(request):
    """Folded into core:settings — kept as a redirect so bookmarks still land.

    The screens are house configuration, not a place anyone spends time, so a
    whole nav entry for two read-only status cards was more prominence than
    they earned.
    """
    return redirect("core:settings")


@login_required
@require_POST
def command(request, slug: str):
    """HTTP fallback for the websocket bus — used by phones and by curl.

    Deliberately accepts exactly what KIOSK_ACTIONS allows and what wall-live.js
    implements, and nothing else. It used to also take show/pin/unpin/wake/
    sleep/next/previous, all left over from the ambient wall the iframe wall
    replaced: the server relayed them, the wall silently ignored every one, and
    a caller got `{"ok": true}` for a command that did nothing. A 400 naming the
    action is more honest than a success that isn't.
    """
    display = get_object_or_404(Display, slug=slug)
    action = request.POST.get("action", "")

    if action == "navigate":
        ok = send_to_display(display.slug, {"type": "navigate",
                                            "path": request.POST.get("path", "")})
    elif action in KIOSK_ACTIONS:
        ok = send_to_display(display.slug, {"type": action})
    else:
        return JsonResponse({"ok": False, "error": f"unknown action {action}"},
                            status=400)

    return JsonResponse({"ok": ok})


@login_required
def status(request):
    # No panel/pinned here: both belong to the rotating ambient wall, and the
    # iframe wall mirrors a real page instead. Reporting them would be reporting
    # fields nothing sets.
    return JsonResponse({
        "displays": [
            {"slug": d.slug, "name": d.name, "kind": d.kind, "online": d.is_online,
             "last_seen": d.last_seen_at.isoformat() if d.last_seen_at else None}
            for d in Display.objects.filter(is_active=True)
        ]
    })
