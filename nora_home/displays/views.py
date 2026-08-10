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


# The bank cycles through these, so two keys side by side are never the same
# colour. Copied from the mockup's own KEY_HUES.
KEY_HUES = ["#38d6ff", "#3ff0b0", "#ffb648", "#ff6b78",
            "#a78bfa", "#7aa2ff", "#a3e635", "#f472b6"]


@login_required
@xframe_options_sameorigin
def kiosk(request):
    """The 10.1" touchscreen — a control desk, not a web page (Story 50).

    An app scroller down the left picks which app the wall shows; that app's
    own `nora_kiosk_controls` become the illuminated key bank, so installing an
    app gives it keys with no platform change. Every key is a path the wall
    navigates to, because navigate/refresh/banner is the entire vocabulary
    wall-live.js implements.

    The desk also carries controls whose capability the platform does not have
    yet — the two faders, the scroll wheel and wall-only power, all owned by
    Story 51. They render *dead* (see `.is-dead` in components.css and the
    template's own comment): present, because the desk's composition is the
    design, but visibly unlit and `disabled`, because a control that moves and
    changes nothing is the "dead button with no error anywhere" this project
    keeps warning about.
    """
    from nora_home.core.registry import wall_apps

    role = getattr(request.user, "role", "member")
    desk = wall_apps(role)
    for index, app in enumerate(desk):
        for key_index, control in enumerate(app["controls"]):
            control["hue"] = KEY_HUES[key_index % len(KEY_HUES)]
        app["index"] = index

    return render(request, "displays/kiosk.html", {
        "target": settings.NORA_HOME_MAIN_DISPLAY_SLUG,
        "wall_apps": desk,
        # The desk opens on Home, and the readout says so. Which app the wall
        # is *actually* on is not stored anywhere today — the wall holds that
        # state in its own iframe — so this is the desk's starting position,
        # not a claim about the wall.
        "current_app": desk[0],
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
