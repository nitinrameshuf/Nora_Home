"""Template context available on every page."""

from __future__ import annotations

from django.conf import settings

from nora_home.core.registry import navigation


def house(request):
    user = getattr(request, "user", None)
    role = getattr(user, "role", "member") if user and user.is_authenticated else "member"
    return {
        "house_name": settings.NORA_HOME_NAME,
        "nora_version": settings.NORA_HOME_VERSION,
        "nora_env": settings.NORA_HOME_ENV,
        "nav": navigation(role),
        "ai_enabled": settings.NORA_HOME_AI_ENABLED,
        "request_id": getattr(request, "request_id", ""),
    }
