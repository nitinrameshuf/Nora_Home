from __future__ import annotations

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from nora_home.core.registry import wall_panels
from nora_home.displays.bus import send_to_display, show_panel
from nora_home.displays.models import Display


@login_required
def wall(request, slug: str = ""):
    """The always-on 24" screen. No chrome, no nav — just the rotating panels.

    It renders every eligible panel once and switches between them client-side, so a
    rotation never waits on a network round trip and a brief outage does not blank
    the wall.
    """
    slug = slug or settings.NORA_HOME_MAIN_DISPLAY_SLUG
    display, _ = Display.objects.get_or_create(
        slug=slug, defaults={"name": slug.title(), "kind": Display.Kind.WALL})

    panels = [p for p in wall_panels() if p.wall_safe]
    return render(request, "displays/wall.html", {
        "display": display,
        "panels": [{"key": p.key, "title": p.title, "html": p.render(request)}
                   for p in panels],
        "rotation_seconds": display.rotation_seconds,
        "night_mode": display.in_night_mode(),
    })


@login_required
@xframe_options_sameorigin
def kiosk(request):
    """The 10.1" touchscreen. Big targets, one thumb, no scrolling required."""
    return render(request, "displays/kiosk.html", {
        "displays": Display.objects.filter(is_active=True),
        "target": settings.NORA_HOME_MAIN_DISPLAY_SLUG,
        "panels": [{"key": p.key, "title": p.title, "icon": p.icon}
                   for p in wall_panels()],
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
