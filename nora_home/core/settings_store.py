"""
Runtime settings a family member can change from the admin, cached in Redis.

    from nora_home.core.settings_store import get_setting, set_setting

    quiet = get_setting("notifications.quiet_hours", default={"start": 22, "end": 7})

Secrets stay in .env — this table is readable by anyone with admin access.
"""

from __future__ import annotations

from django.core.cache import cache

CACHE_PREFIX = "house_setting:"
CACHE_TTL = 300


def get_setting(key: str, default=None):
    cache_key = CACHE_PREFIX + key
    cached = cache.get(cache_key)
    if cached is not None:
        return cached["value"]

    from nora_home.core.models import HouseSetting

    try:
        setting = HouseSetting.objects.get(key=key)
    except HouseSetting.DoesNotExist:
        return default
    cache.set(cache_key, {"value": setting.value}, CACHE_TTL)
    return setting.value


def set_setting(key: str, value, *, app_slug: str = "", description: str = ""):
    from nora_home.core.models import HouseSetting

    setting, _ = HouseSetting.objects.update_or_create(
        key=key,
        defaults={"value": value, "app_slug": app_slug, "description": description},
    )
    cache.delete(CACHE_PREFIX + key)
    return setting


def invalidate(key: str):
    cache.delete(CACHE_PREFIX + key)
