"""Template context available on every page."""

from __future__ import annotations

from django.conf import settings

from nora_home.core.registry import navigation, palette_destinations
from nora_home.core.vitals import rail_vitals


def house(request):
    user = getattr(request, "user", None)
    authenticated = bool(user and user.is_authenticated)
    role = getattr(user, "role", "member") if authenticated else "member"
    view_scope = request.session.get("nh_view_scope", "self") if hasattr(request, "session") else "self"

    active_members = []
    if authenticated:
        from nora_home.accounts.models import HouseMember
        active_members = list(HouseMember.objects.filter(is_active=True))

    return {
        "house_name": settings.NORA_HOME_NAME,
        "nora_version": settings.NORA_HOME_VERSION,
        "nora_env": settings.NORA_HOME_ENV,
        "nav": navigation(role),
        # The ⌘K palette (Story 47) — computed here rather than in JS so it's
        # grounded in the same registry the nav itself reads, not a second,
        # hand-maintained list that can drift from what's actually installed.
        "nh_palette": palette_destinations(role) if authenticated else [],
        # The console rail's vitals (Story 48). Cheap local file reads only —
        # see nora_home.core.vitals on why this must never call collect_health().
        "nh_vitals": rail_vitals() if authenticated else [],
        "ai_enabled": settings.NORA_HOME_AI_ENABLED,
        "request_id": getattr(request, "request_id", ""),
        "active_members": active_members,
        "nh_view_scope": view_scope,
    }
