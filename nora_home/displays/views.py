from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from nora_home.core.registry import navigation
from nora_home.displays.bus import send_to_display, show_panel
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
        "displays": Display.objects.filter(is_active=True),
        "target": settings.NORA_HOME_MAIN_DISPLAY_SLUG,
        "nav": nav,
        "apps_with_controls": apps_with_controls,
        "home_url": reverse("core:dashboard"),
        "alerts_url": reverse("notifications:inbox"),
        "house_links": [
            {"title": "Apps", "url": reverse("core:app_directory")},
            {"title": "Status", "url": reverse("core:system_status")},
            {"title": "Settings", "url": reverse("core:settings")},
        ],
    })


@login_required
def manage(request):
    return render(request, "displays/manage.html", {
        "displays": Display.objects.all(),
        "page_title": "Displays",
    })


@login_required
@require_POST
def command(request, slug: str):
    """HTTP fallback for the websocket bus — used by phones and by curl."""
    display = get_object_or_404(Display, slug=slug)
    action = request.POST.get("action", "")

    if action == "show":
        ok = show_panel(display.slug, request.POST.get("panel", ""),
                        pin_seconds=int(request.POST.get("pin_seconds", 0) or 0),
                        issued_by=request.user.get_username())
    elif action == "navigate":
        ok = send_to_display(display.slug, {"type": "navigate",
                                            "path": request.POST.get("path", "")})
    elif action in {"refresh", "wake", "sleep", "next", "previous", "unpin"}:
        if action == "unpin":
            display.pinned_until = None
            display.save(update_fields=["pinned_until", "updated_at"])
        ok = send_to_display(display.slug, {"type": action})
    else:
        return JsonResponse({"ok": False, "error": f"unknown action {action}"},
                            status=400)

    return JsonResponse({"ok": ok})


@login_required
def status(request):
    return JsonResponse({
        "displays": [
            {"slug": d.slug, "name": d.name, "kind": d.kind, "online": d.is_online,
             "panel": d.current_panel, "pinned": d.is_pinned,
             "last_seen": d.last_seen_at.isoformat() if d.last_seen_at else None}
            for d in Display.objects.filter(is_active=True)
        ]
    })
