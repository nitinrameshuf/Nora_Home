"""
The living background's two axes — time of day, weather. Story 46 removed
season and the landscape entirely (CLAUDE.md §4, Phase 8): the arc-reactor
scene is a sky, a celestial body, and visible weather, nothing else.

Computed once here and shared by the context processor (first paint, so there's
no flash of the wrong sky) and the JSON endpoint the wall and kiosk poll every
few minutes to stay live without a full page reload — so the two can never
disagree about what moment it currently is.

    from nora_home.ui.scene import current_scene

    current_scene()  # -> {"daypart": "dusk", "weather": "clear", ...}

Weather degrades gracefully, falling back to "clear" until the weather
integration has run at least once.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from django.utils import timezone as djtz

# How close to actual sunrise/sunset counts as "dawn"/"dusk" rather than
# "noon"/"night" — wide enough to read clearly on screen, narrow enough that
# most of the day still reads as full daylight.
_TWILIGHT_WINDOW = timedelta(minutes=45)


def daypart_for(now: datetime, sunrise_iso: str = "", sunset_iso: str = "") -> str:
    """dawn / noon / dusk / night, from the real sunrise and sunset the weather
    integration already fetched. Falls back to fixed clock hours if the
    integration hasn't run yet (fresh install, or Open-Meteo unreachable)."""
    naive_now = djtz.localtime(now).replace(tzinfo=None) if djtz.is_aware(now) else now
    sunrise = _parse_naive(sunrise_iso)
    sunset = _parse_naive(sunset_iso)

    if sunrise is None or sunset is None:
        hour = naive_now.hour
        if 5 <= hour < 8:
            return "dawn"
        if 8 <= hour < 17:
            return "noon"
        if 17 <= hour < 20:
            return "dusk"
        return "night"

    if abs(naive_now - sunrise) <= _TWILIGHT_WINDOW:
        return "dawn"
    if abs(naive_now - sunset) <= _TWILIGHT_WINDOW:
        return "dusk"
    if sunrise + _TWILIGHT_WINDOW < naive_now < sunset - _TWILIGHT_WINDOW:
        return "noon"
    return "night"


def _parse_naive(iso: str) -> datetime | None:
    if not iso:
        return None
    try:
        return datetime.fromisoformat(iso).replace(tzinfo=None)
    except ValueError:
        return None


def current_scene() -> dict:
    from nora_home.core.settings_store import get_setting

    # This runs in a context processor, on the first paint of every page in the
    # house. The value is JSON a person can edit in the admin, so anything that
    # is not a dict has to degrade to "no weather yet" rather than raising —
    # otherwise one bad edit 500s every screen at once, including the wall.
    weather = get_setting("weather.current", default={})
    if not isinstance(weather, dict):
        weather = {}
    now = djtz.localtime()
    return {
        "daypart": daypart_for(now, weather.get("sunrise", ""), weather.get("sunset", "")),
        "weather": weather.get("condition", "clear"),
        "temp_c": weather.get("temp_c"),
        "updated_at": weather.get("updated_at", ""),
    }
