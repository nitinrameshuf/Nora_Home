"""
Surface detection.

The same pages have to work on a phone in a pocket, an iPad on a counter, a laptop,
the 24" wall display across the room, and the 10.1" kiosk under someone's thumb.
Rather than guessing from viewport width alone, the platform names the *surface* and
lets templates and CSS respond to it.

    wall     the always-on 1080p screen — read from three metres, never touched
    kiosk    the 10.1" touchscreen — huge targets, one hand, no keyboard
    phone    a pocket screen
    tablet   an iPad
    desktop  a laptop or monitor with a pointer

The URL decides for wall and kiosk (those are fixed-purpose pages); the User-Agent
decides for the rest, and a `nh_surface` cookie overrides everything so someone can
force a mode from the settings page.
"""

from __future__ import annotations

import re

WALL_PREFIXES = ("/home/displays/wall",)
KIOSK_PREFIXES = ("/home/displays/kiosk",)

VALID_SURFACES = {"wall", "kiosk", "phone", "tablet", "desktop"}

PHONE_RE = re.compile(r"iphone|android.+mobile|windows phone|ipod", re.I)
TABLET_RE = re.compile(r"ipad|android(?!.+mobile)|tablet|silk", re.I)


class SurfaceMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.nh_surface = self._detect(request)
        request.nh_is_touch = request.nh_surface in {"kiosk", "phone", "tablet"}
        response = self.get_response(request)
        response["X-Nora-Surface"] = request.nh_surface
        return response

    def _detect(self, request) -> str:
        path = request.path
        if path.startswith(WALL_PREFIXES):
            return "wall"
        if path.startswith(KIOSK_PREFIXES):
            return "kiosk"

        # The wall shows the *real app* through a same-origin iframe
        # (nora_home.displays.views.wall / wall_live.html) — every page that
        # iframe loads needs to know it is rendering for the wall too, not
        # just the shell page above matched by WALL_PREFIXES. Sec-Fetch-Dest
        # is the browser's own signal that a document was loaded as an
        # iframe (sent by every Chromium this house's screens run); the
        # Referer, sent because SECURE_REFERRER_POLICY is "same-origin" and
        # this is one, confirms the parent was specifically the wall's own
        # page rather than someone iframing the app for an unrelated reason.
        # Stateless on purpose — no cookie, so a stray visit to the app from
        # someone's own laptop is never at risk of getting stuck "wall"-sized.
        if request.META.get("HTTP_SEC_FETCH_DEST") == "iframe":
            referer = request.META.get("HTTP_REFERER", "")
            if any(prefix in referer for prefix in WALL_PREFIXES):
                return "wall"

        override = request.COOKIES.get("nh_surface", "")
        if override in VALID_SURFACES:
            return override

        agent = request.META.get("HTTP_USER_AGENT", "")
        if PHONE_RE.search(agent):
            return "phone"
        if TABLET_RE.search(agent):
            return "tablet"
        return "desktop"
