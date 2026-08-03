"""
Weather — the first concrete integration, and the real data source behind the
living background's weather axis (season and time-of-day need no integration
at all; only "what's it doing outside right now" has to come from somewhere).

No API key: Open-Meteo is free and unauthenticated, keyed only by latitude and
longitude (NORA_HOME_LAT / NORA_HOME_LON). It also returns today's sunrise and
sunset, which nora_home.ui.scene reuses for real dawn/dusk timing instead of
guessing from fixed clock hours.
"""

from __future__ import annotations

from django.conf import settings

from nora_home.integrations.base import Integration, IntegrationError, register

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

# WMO weather codes (what Open-Meteo's `current.weather_code` returns),
# bucketed into the four states the living background actually renders.
# https://open-meteo.com/en/docs#weathervariables
_CLEAR = {0, 1}
_CLOUDY = {2, 3, 45, 48}
_RAIN = {51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99}
_SNOW = {71, 73, 75, 77, 85, 86}


def bucket_condition(code: int) -> str:
    if code in _SNOW:
        return "snow"
    if code in _RAIN:
        return "rain"
    if code in _CLOUDY:
        return "cloudy"
    return "clear"


@register
class Weather(Integration):
    slug = "weather"
    name = "Weather"
    description = ("Outside temperature and condition, from Open-Meteo — no API "
                   "key needed, just the house's location.")
    default_interval_minutes = 15

    def fetch(self) -> dict:
        lat, lon = settings.NORA_HOME_LAT, settings.NORA_HOME_LON
        if lat is None or lon is None:
            raise IntegrationError(
                "NORA_HOME_LAT / NORA_HOME_LON are not set — the living background "
                "can't know the weather or the real sunrise/sunset without them.")

        data = self.get(OPEN_METEO_URL, params={
            "latitude": lat,
            "longitude": lon,
            "current": "temperature_2m,weather_code",
            "daily": "sunrise,sunset",
            "timezone": "auto",
        })

        try:
            current = data["current"]
            code = int(current["weather_code"])
            temp_c = float(current["temperature_2m"])
            sunrise = data["daily"]["sunrise"][0]
            sunset = data["daily"]["sunset"][0]
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise IntegrationError(f"Unexpected Open-Meteo response shape: {exc}") from exc

        condition = bucket_condition(code)
        self._store(condition, code, temp_c, sunrise, sunset)
        self._record_temperature(temp_c)

        return {"condition": condition, "temp_c": temp_c}

    def _record_temperature(self, temp_c: float):
        from nora_home.telemetry.api import define_series

        # Named and categorised explicitly rather than left to record()'s
        # auto-create fallback, which would otherwise title-case the raw key
        # ("Weather Temperature_C") — this is what shows up in HouseVitalsWidget.
        define_series("weather.temperature_c", "Outside temperature", unit="°C",
                      app_slug="integrations", category="house", precision=1)
        self.record("temperature_c", temp_c)

    def _store(self, condition: str, code: int, temp_c: float, sunrise: str, sunset: str):
        from django.utils import timezone as djtz

        from nora_home.core.settings_store import set_setting

        set_setting(
            "weather.current",
            {
                "condition": condition,
                "weather_code": code,
                "temp_c": round(temp_c, 1),
                "sunrise": sunrise,
                "sunset": sunset,
                "updated_at": djtz.now().isoformat(),
            },
            app_slug="integrations",
            description="Current outside conditions — powers the living background "
                        "and the weather widget.",
        )
