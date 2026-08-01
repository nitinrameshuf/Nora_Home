from __future__ import annotations

from django.conf import settings


def surface(request):
    current = getattr(request, "nh_surface", "desktop")
    return {
        "surface": current,
        "is_touch": getattr(request, "nh_is_touch", False),
        "is_wall": current == "wall",
        "is_kiosk": current == "kiosk",
        # The home bot stays quiet on the wall display; nobody is there to talk to,
        # and a sprite zipping around an always-on screen is exhausting.
        "nh_bot_enabled": current != "wall",
        "main_display_slug": settings.NORA_HOME_MAIN_DISPLAY_SLUG,
    }
