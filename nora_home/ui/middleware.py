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
from urllib.parse import urlsplit

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
        # is the browser's own signal that a document was loaded as an iframe
        # (sent by every Chromium this house's screens run).
        #
        # Two referers count, and the second is not an optimisation:
        #
        #   1. the wall's own shell page — the first hop, when the kiosk
        #      points the iframe somewhere;
        #   2. *any* same-origin page — every hop after that.
        #
        # Only (1) existed until 2026-08-07, and it silently broke the moment
        # anyone used the 24" directly: clicking a link inside the iframe
        # leaves the previous *app* page as the referer, not the shell, so the
        # wall fell back to User-Agent and rendered at laptop scale with the
        # wall's zoom dropped. Nothing errored; the screen just quietly
        # stopped being the wall until the kiosk drove it again.
        #
        # (2) is safe because it is same-origin: a page on another origin
        # embedding this app either sends no Referer or sends its own, and
        # fails the host check either way. What it does trust is that nothing
        # in this house iframes an app page except the wall — true today, and
        # worth remembering before adding a second iframe anywhere.
        #
        # Still stateless — no cookie — so a stray visit to the app from
        # someone's own laptop is never at risk of getting stuck "wall"-sized.
        if request.META.get("HTTP_SEC_FETCH_DEST") == "iframe":
            referer = request.META.get("HTTP_REFERER", "")
            if any(prefix in referer for prefix in WALL_PREFIXES):
                return "wall"
            if self._is_same_origin(request, referer):
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

    @staticmethod
    def _is_same_origin(request, referer: str) -> bool:
        """Does `referer` point back at this same house?

        Hostname only, deliberately ignoring the port: the wall's Chromium is
        launched at `https://localhost:443/...` while the browser drops the
        default port from both the Host header and the Referer it sends, so a
        strict netloc comparison would be comparing values the browser has
        already normalised differently at each end.
        """
        if not referer:
            return False
        try:
            host = urlsplit(referer).hostname
        except ValueError:      # a malformed Referer is not worth an error page
            return False
        return bool(host) and host == request.get_host().partition(":")[0]
