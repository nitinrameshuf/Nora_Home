"""
Dashboard cards and wall panels.

A card is the unit of "what my app wants to say on the home screen". Keep the
`context()` call cheap — the dashboard renders every card on one request, and the
wall display re-renders on a timer forever.

    from nora_home.core.cards import Card

    class WeekVolumeCard(Card):
        title = "This week"
        template = "workout/cards/week_volume.html"
        size = "medium"
        refresh_seconds = 300

        def context(self, request):
            return {"sets": Set.objects.this_week().count()}

If context() raises, the platform renders a small "unavailable" tile instead of a
500 — one app's bad query must not blank the wall.
"""

from __future__ import annotations

import logging
from importlib import import_module

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

SIZES = {"small", "medium", "large", "wide", "full"}


class Card:
    title: str = ""
    subtitle: str = ""
    template: str = ""
    icon: str = ""
    size: str = "medium"
    order: int = 100
    refresh_seconds: int = 0  # 0 = never auto-refresh
    wall_safe: bool = True  # may this render on the always-on display?

    def __init__(self, app_meta=None):
        self.app = app_meta

    @property
    def key(self) -> str:
        slug = getattr(self.app, "slug", "core")
        return f"{slug}.{type(self).__name__}"

    def context(self, request) -> dict:  # noqa: ARG002
        return {}

    def is_visible(self, request) -> bool:  # noqa: ARG002
        return True

    def render(self, request) -> str:
        if not self.template:
            return ""
        try:
            ctx = {"card": self, "app": self.app, **self.context(request)}
        except Exception:
            logger.exception("Card %s failed to build context", self.key)
            return render_to_string("core/cards/_unavailable.html",
                                    {"card": self}, request=request)
        try:
            return render_to_string(self.template, ctx, request=request)
        except Exception:
            logger.exception("Card %s failed to render", self.key)
            return render_to_string("core/cards/_unavailable.html",
                                    {"card": self}, request=request)


def load_card(dotted: str, app_meta=None) -> Card | None:
    """Import 'pkg.module.ClassName' and instantiate it. Returns None on failure."""
    try:
        module_path, class_name = dotted.rsplit(".", 1)
        klass = getattr(import_module(module_path), class_name)
    except Exception:
        logger.exception("Could not load dashboard card %s", dotted)
        return None
    if not issubclass(klass, Card):
        logger.error("%s is declared as a card but does not subclass nora_home.core.cards.Card",
                     dotted)
        return None
    if klass.size not in SIZES:
        logger.warning("Card %s has unknown size %r; using medium", dotted, klass.size)
        klass.size = "medium"
    return klass(app_meta)
