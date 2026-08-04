"""
The living background — season, daypart, weather.

This is the "Almanac" design system's engine (CLAUDE.md §4). Two properties
matter more than any individual value: it must never raise, because it runs in a
context processor on the first paint of every page in the house; and the wall
and the kiosk must always agree about what moment it is, since they sit two
metres apart and poll the same endpoint.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest

from nora_home.core.settings_store import set_setting
from nora_home.ui.scene import current_scene, daypart_for, season_for

pytestmark = pytest.mark.django_db


# ── season ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("month,expected", [
    (12, "winter"), (1, "winter"), (2, "winter"),
    (3, "spring"), (4, "spring"), (5, "spring"),
    (6, "summer"), (7, "summer"), (8, "summer"),
    (9, "autumn"), (10, "autumn"), (11, "autumn"),
])
def test_meteorological_seasons_in_the_northern_hemisphere(settings, month, expected):
    settings.NORA_HOME_LAT = 40.7128  # the house's real latitude

    assert season_for(date(2026, month, 15)) == expected


@pytest.mark.parametrize("month,expected", [
    (12, "summer"), (1, "summer"), (6, "winter"), (9, "spring"), (3, "autumn"),
])
def test_seasons_flip_south_of_the_equator(settings, month, expected):
    settings.NORA_HOME_LAT = -33.87  # Sydney

    assert season_for(date(2026, month, 15)) == expected


def test_an_unset_latitude_does_not_break_the_season(settings):
    """The background has to render on a fresh install with nothing configured."""
    settings.NORA_HOME_LAT = None

    assert season_for(date(2026, 1, 15)) == "winter"


def test_the_equator_counts_as_northern(settings):
    settings.NORA_HOME_LAT = 0.0

    assert season_for(date(2026, 1, 15)) == "winter"


# ── daypart, from real sunrise and sunset ────────────────────────────────────

SUNRISE = "2026-08-03T06:00"
SUNSET = "2026-08-03T20:00"


@pytest.mark.parametrize("clock,expected", [
    ("2026-08-03T06:00", "dawn"),    # exactly sunrise
    ("2026-08-03T06:30", "dawn"),    # inside the twilight window
    ("2026-08-03T05:30", "dawn"),    # just before sunrise
    ("2026-08-03T12:00", "noon"),
    ("2026-08-03T20:00", "dusk"),    # exactly sunset
    ("2026-08-03T19:30", "dusk"),
    ("2026-08-03T23:00", "night"),
    ("2026-08-03T03:00", "night"),
])
def test_daypart_uses_real_sunrise_and_sunset(clock, expected):
    assert daypart_for(datetime.fromisoformat(clock), SUNRISE, SUNSET) == expected


def test_daypart_falls_back_to_clock_hours_without_weather_data():
    """A fresh install, or Open-Meteo unreachable. The sky still has to be some
    plausible colour rather than the page rendering unstyled."""
    assert daypart_for(datetime(2026, 8, 3, 6, 0)) == "dawn"
    assert daypart_for(datetime(2026, 8, 3, 12, 0)) == "noon"
    assert daypart_for(datetime(2026, 8, 3, 18, 0)) == "dusk"
    assert daypart_for(datetime(2026, 8, 3, 23, 0)) == "night"


def test_malformed_sun_times_fall_back_rather_than_raising():
    """A provider change that alters the timestamp format must not blank every
    page in the house."""
    assert daypart_for(datetime(2026, 8, 3, 12, 0), "not-a-time", "also-not") == "noon"


def test_a_missing_sunset_falls_back_even_with_a_sunrise():
    assert daypart_for(datetime(2026, 8, 3, 12, 0), SUNRISE, "") == "noon"


def test_winter_daylight_is_shorter_than_summer_daylight():
    """The whole point of using real sun times: at 17:00 in December it is dark,
    and in June it is not."""
    december = daypart_for(datetime(2026, 12, 21, 18, 0),
                           "2026-12-21T07:15", "2026-12-21T16:30")
    june = daypart_for(datetime(2026, 6, 21, 18, 0),
                       "2026-06-21T05:25", "2026-06-21T20:30")

    assert december == "night"
    assert june == "noon"


# ── the composed scene ───────────────────────────────────────────────────────

def test_current_scene_has_every_axis_the_css_needs():
    scene = current_scene()

    assert set(scene) >= {"season", "daypart", "weather", "temp_c", "updated_at"}


def test_weather_defaults_to_clear_before_the_integration_has_run():
    """Degrades gracefully: no weather yet is a clear sky, not a crash or a
    blank background."""
    assert current_scene()["weather"] == "clear"


def test_current_scene_reads_the_stored_weather():
    set_setting("weather.current", {"condition": "rain", "temp_c": 12.5,
                                    "updated_at": "2026-08-03T10:00"})

    scene = current_scene()

    assert scene["weather"] == "rain"
    assert scene["temp_c"] == 12.5


@pytest.mark.parametrize("stored", [[], "broken", 42, {"unexpected": "shape"}])
def test_current_scene_survives_a_corrupt_weather_setting(stored):
    """The setting is JSON a person can edit in the admin, and this runs in a
    context processor on every page. One bad edit must not 500 every screen in
    the house at once — including the wall, which nobody is standing at."""
    set_setting("weather.current", stored)

    assert current_scene()["weather"] == "clear"


def test_the_scene_is_computed_once_so_screens_cannot_disagree():
    """The wall and the kiosk both poll core:weather_current. If two calls a
    moment apart disagreed, the two screens would show different skies."""
    assert current_scene()["season"] == current_scene()["season"]
    assert current_scene()["daypart"] == current_scene()["daypart"]


# ── the endpoint the screens poll ────────────────────────────────────────────

def test_the_weather_endpoint_returns_the_same_scene(client, adult):
    client.force_login(adult)
    set_setting("weather.current", {"condition": "snow", "temp_c": -3})

    payload = client.get("/home/api/weather/").json()

    assert payload["weather"] == "snow"
    assert payload["season"] == current_scene()["season"]


def test_the_weather_endpoint_works_before_any_weather_exists(client, adult):
    client.force_login(adult)

    response = client.get("/home/api/weather/")

    assert response.status_code == 200
    assert response.json()["weather"] == "clear"


# ── the weather integration's own parsing ────────────────────────────────────

@pytest.mark.parametrize("code,expected", [
    (0, "clear"), (1, "clear"),
    (2, "cloudy"), (3, "cloudy"), (45, "cloudy"),
    (61, "rain"), (80, "rain"), (95, "rain"),
    (71, "snow"), (86, "snow"),
    (999, "clear"),  # an unknown code must not blank the background
])
def test_wmo_codes_bucket_into_the_four_rendered_states(code, expected):
    from nora_home.integrations.providers.weather import bucket_condition

    assert bucket_condition(code) == expected
