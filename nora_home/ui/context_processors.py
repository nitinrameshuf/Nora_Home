from __future__ import annotations

from django.conf import settings


def surface(request):
    from nora_home.ui import zoom as zoom_settings

    current = getattr(request, "nh_surface", "desktop")
    return {
        "surface": current,
        # None on a phone or laptop, so their markup carries no zoom at all —
        # those are held at arm's length, which is what the browser already
        # assumes. See nora_home/ui/zoom.py.
        "nh_zoom": zoom_settings.for_surface(current),
        "is_touch": getattr(request, "nh_is_touch", False),
        "is_wall": current == "wall",
        "is_kiosk": current == "kiosk",
        # The home bot stays quiet on the wall display; nobody is there to talk to,
        # and a sprite zipping around an always-on screen is exhausting.
        "nh_bot_enabled": current != "wall",
        "main_display_slug": settings.NORA_HOME_MAIN_DISPLAY_SLUG,
    }


def scene(request):
    """Season / time-of-day / weather for the living background — computed
    server-side so the first paint is already correct, then kept fresh
    client-side by nh-scene.js polling the same computation (core:weather_current)."""
    from nora_home.ui.scene import current_scene

    data = current_scene()
    return {
        "nh_season": data["season"],
        "nh_daypart": data["daypart"],
        "nh_weather": data["weather"],
        "nh_weather_temp_c": data["temp_c"],
    }
