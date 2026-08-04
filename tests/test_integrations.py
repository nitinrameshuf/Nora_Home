"""
The integration framework: scheduling, backoff, and failure alerting.

Integrations are the one subsystem whose whole job is talking to things outside
the house, which makes them the one place a test must be most careful *not* to.
Nothing here makes a network call — the HTTP helpers are exercised against a
fake transport, and the weather provider is driven with a recorded Open-Meteo
payload rather than the live API.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
import requests
from django.utils import timezone

from nora_home.core.settings_store import get_setting
from nora_home.core.signals import integration_synced
from nora_home.integrations.base import (
    Integration as IntegrationBase,
)
from nora_home.integrations.base import (
    IntegrationError,
    available,
    get_class,
    register,
)
from nora_home.integrations.models import Integration, IntegrationRun
from nora_home.integrations.tasks import (
    FAILURE_ALERT_THRESHOLD,
    poll_due_integrations,
    run_integration,
)
from nora_home.notifications.models import Notification
from nora_home.telemetry.models import Series

pytestmark = pytest.mark.django_db


# ── scheduling ───────────────────────────────────────────────────────────────

def test_a_never_run_integration_is_due():
    record = Integration.objects.create(slug="weather", name="Weather")

    assert record.is_due is True


def test_a_recently_run_integration_is_not_due():
    record = Integration.objects.create(slug="weather", name="Weather",
                                        interval_minutes=15,
                                        last_run_at=timezone.now())

    assert record.is_due is False


def test_an_integration_becomes_due_after_its_interval():
    record = Integration.objects.create(
        slug="weather", name="Weather", interval_minutes=15,
        last_run_at=timezone.now() - timedelta(minutes=16))

    assert record.is_due is True


def test_a_disabled_integration_is_never_due():
    record = Integration.objects.create(slug="weather", name="Weather",
                                        is_enabled=False)

    assert record.is_due is False


def test_failures_back_off_exponentially():
    """A dead service should be polled every few hours, not every few minutes —
    otherwise a wifi outage becomes a self-inflicted denial of service on the
    house's own worker."""
    record = Integration.objects.create(
        slug="weather", name="Weather", interval_minutes=15,
        consecutive_failures=3,
        last_run_at=timezone.now() - timedelta(minutes=30))

    assert record.is_due is False, "backoff was not applied"

    record.last_run_at = timezone.now() - timedelta(minutes=121)  # 15 × 2³ = 120
    assert record.is_due is True


def test_backoff_is_capped():
    """Uncapped, 2**failures overflows into never polling again — the
    integration would be permanently dead with no error to show for it."""
    record = Integration.objects.create(
        slug="weather", name="Weather", interval_minutes=15,
        consecutive_failures=40,
        last_run_at=timezone.now() - timedelta(minutes=15 * 16 + 1))

    assert record.is_due is True


def test_health_tracks_consecutive_failures():
    record = Integration.objects.create(slug="weather", name="Weather")
    assert record.is_healthy is True

    record.consecutive_failures = 1
    assert record.is_healthy is False


def test_polling_dispatches_only_what_is_due(settings):
    settings.CELERY_TASK_ALWAYS_EAGER = True
    Integration.objects.create(slug="unknown_a", name="Due now")
    Integration.objects.create(slug="unknown_b", name="Not due",
                               last_run_at=timezone.now())
    Integration.objects.create(slug="unknown_c", name="Disabled", is_enabled=False)

    assert poll_due_integrations()["dispatched"] == 1


# ── running ──────────────────────────────────────────────────────────────────

@pytest.fixture
def fake_integration():
    """A registered integration whose behaviour each test sets. Removed from the
    registry afterwards so it cannot leak into other tests."""
    from nora_home.integrations.base import _REGISTRY

    behaviour = {"fetch": lambda self: {"records": 1}}

    @register
    class Fake(IntegrationBase):
        slug = "fake"
        name = "Fake"
        config_fields = {"base_url": "http://example.invalid"}

        def fetch(self):
            return behaviour["fetch"](self)

    yield behaviour
    _REGISTRY.pop("fake", None)


def test_a_successful_run_is_recorded(fake_integration):
    record = Integration.objects.create(slug="fake", name="Fake")

    result = run_integration(record.pk)

    record.refresh_from_db()
    assert result["ok"] is True
    assert record.last_success_at is not None
    assert record.consecutive_failures == 0
    assert IntegrationRun.objects.get().succeeded is True


def test_a_successful_run_clears_a_previous_error(fake_integration):
    record = Integration.objects.create(slug="fake", name="Fake",
                                        consecutive_failures=5,
                                        last_error="it was broken")

    run_integration(record.pk)

    record.refresh_from_db()
    assert record.consecutive_failures == 0
    assert record.last_error == ""


def test_an_expected_failure_is_recorded_without_a_traceback(fake_integration):
    def fail(self):
        raise IntegrationError("service unavailable")

    fake_integration["fetch"] = fail
    record = Integration.objects.create(slug="fake", name="Fake")

    result = run_integration(record.pk)

    record.refresh_from_db()
    assert result["ok"] is False
    assert record.consecutive_failures == 1
    assert "service unavailable" in record.last_error


def test_an_unexpected_exception_is_caught_too(fake_integration):
    """A bug in one integration must not kill the worker that runs all of them."""
    def explode(self):
        raise ValueError("bad payload shape")

    fake_integration["fetch"] = explode
    record = Integration.objects.create(slug="fake", name="Fake")

    result = run_integration(record.pk)

    assert result["ok"] is False
    assert "ValueError" in Integration.objects.get().last_error


def test_failures_accumulate(fake_integration):
    def fail(self):
        raise IntegrationError("still down")

    fake_integration["fetch"] = fail
    record = Integration.objects.create(slug="fake", name="Fake")

    run_integration(record.pk)
    run_integration(record.pk)

    record.refresh_from_db()
    assert record.consecutive_failures == 2


def test_the_house_is_told_once_after_repeated_failures(fake_integration):
    """Once, not every cycle — an integration that has been down for a week
    should not have produced a thousand banners."""
    def fail(self):
        raise IntegrationError("still down")

    fake_integration["fetch"] = fail
    record = Integration.objects.create(slug="fake", name="Fake")

    for _ in range(FAILURE_ALERT_THRESHOLD + 4):
        run_integration(record.pk)

    assert Notification.objects.count() == 1


def test_the_house_is_not_told_about_a_single_blip(fake_integration):
    def fail(self):
        raise IntegrationError("transient")

    fake_integration["fetch"] = fail
    record = Integration.objects.create(slug="fake", name="Fake")

    run_integration(record.pk)

    assert Notification.objects.count() == 0


def test_a_successful_run_fires_integration_synced(fake_integration,
                                                   signal_recorder):
    signal_recorder.watch(integration_synced)
    record = Integration.objects.create(slug="fake", name="Fake")

    run_integration(record.pk)

    assert len(signal_recorder.calls) == 1


def test_running_an_unregistered_slug_is_survivable():
    record = Integration.objects.create(slug="not_registered", name="Ghost")

    result = run_integration(record.pk)

    assert result["ok"] is False
    assert "unknown integration" in result["error"]


def test_running_a_deleted_integration_is_survivable():
    assert run_integration(999999)["ok"] is False


# ── the base class's helpers ─────────────────────────────────────────────────

def test_config_defaults_are_merged_with_stored_config(fake_integration):
    record = Integration.objects.create(slug="fake", name="Fake",
                                        config={"extra": 1})

    instance = get_class("fake")(record)

    assert instance.config == {"base_url": "http://example.invalid", "extra": 1}


def test_stored_config_overrides_the_default(fake_integration):
    record = Integration.objects.create(slug="fake", name="Fake",
                                        config={"base_url": "http://real.invalid"})

    assert get_class("fake")(record).config["base_url"] == "http://real.invalid"


def test_secrets_come_from_the_environment_never_the_database(fake_integration,
                                                              monkeypatch):
    """"Secrets never go in the database" (CLAUDE.md §4) — a database dump
    shared for debugging must carry no tokens."""
    monkeypatch.setenv("NORA_HOME_INTEGRATION_FAKE_TOKEN", "s3cret")
    record = Integration.objects.create(slug="fake", name="Fake")

    assert get_class("fake")(record).secret("token") == "s3cret"


def test_a_missing_secret_raises_a_useful_error(fake_integration, monkeypatch):
    monkeypatch.delenv("NORA_HOME_INTEGRATION_FAKE_TOKEN", raising=False)
    record = Integration.objects.create(slug="fake", name="Fake")

    with pytest.raises(IntegrationError) as caught:
        get_class("fake")(record).secret("token")

    assert "NORA_HOME_INTEGRATION_FAKE_TOKEN" in str(caught.value), (
        "the error should name the variable to set")


def test_a_network_error_becomes_an_integration_error(fake_integration,
                                                      monkeypatch):
    """Anything else and one unreachable service raises a raw requests exception
    into the worker, which is treated as a bug and logged with a traceback."""
    def boom(*args, **kwargs):
        raise requests.ConnectionError("no route to host")

    monkeypatch.setattr(requests, "get", boom)
    record = Integration.objects.create(slug="fake", name="Fake")

    with pytest.raises(IntegrationError):
        get_class("fake")(record).get("http://example.invalid")


def test_http_calls_always_carry_a_timeout(fake_integration, monkeypatch):
    """Without one, a hung service holds a worker forever and the escalation
    queue stops moving behind it."""
    seen = {}

    class FakeResponse:
        content = b"{}"

        @staticmethod
        def raise_for_status():
            return None

        @staticmethod
        def json():
            return {}

    def capture(url, **kwargs):
        seen.update(kwargs)
        return FakeResponse()

    monkeypatch.setattr(requests, "get", capture)
    record = Integration.objects.create(slug="fake", name="Fake")

    get_class("fake")(record).get("http://example.invalid")

    assert seen.get("timeout"), "no timeout was passed"


def test_recording_namespaces_the_series_under_the_integration(fake_integration):
    """Two integrations both reporting "temperature" must not collide."""
    record = Integration.objects.create(slug="fake", name="Fake")

    get_class("fake")(record).record("temperature", 21.0)

    assert Series.objects.filter(key="fake.temperature").exists()


# ── the registry ─────────────────────────────────────────────────────────────

def test_registering_without_a_slug_is_refused():
    with pytest.raises(ValueError):
        @register
        class Nameless(IntegrationBase):
            pass


def test_the_weather_provider_is_registered():
    assert "weather" in available()


def test_get_class_returns_none_for_an_unknown_slug():
    assert get_class("not_a_real_integration") is None


# ── the weather provider ─────────────────────────────────────────────────────

OPEN_METEO_RESPONSE = {
    "current": {"temperature_2m": 24.8, "weather_code": 3},
    "daily": {"sunrise": ["2026-08-03T06:01"], "sunset": ["2026-08-03T20:10"]},
}


def test_weather_stores_what_the_living_background_reads(monkeypatch, settings):
    """The provider and nora_home.ui.scene meet at one HouseSetting key. If the
    shape written here stops matching what scene.py reads, the background
    silently reverts to a clear sky with no error anywhere."""
    settings.NORA_HOME_LAT = 40.7128
    settings.NORA_HOME_LON = -74.0060
    monkeypatch.setattr(IntegrationBase, "get",
                        lambda self, url, **kwargs: OPEN_METEO_RESPONSE)
    record = Integration.objects.create(slug="weather", name="Weather")

    run_integration(record.pk)

    stored = get_setting("weather.current")
    assert stored["condition"] == "cloudy"
    assert stored["temp_c"] == 24.8
    assert stored["sunrise"] == "2026-08-03T06:01"
    assert stored["sunset"] == "2026-08-03T20:10"


def test_weather_feeds_the_scene_end_to_end(monkeypatch, settings):
    from nora_home.ui.scene import current_scene

    settings.NORA_HOME_LAT = 40.7128
    settings.NORA_HOME_LON = -74.0060
    monkeypatch.setattr(IntegrationBase, "get",
                        lambda self, url, **kwargs: OPEN_METEO_RESPONSE)
    record = Integration.objects.create(slug="weather", name="Weather")

    run_integration(record.pk)

    assert current_scene()["weather"] == "cloudy"


def test_weather_without_a_location_fails_with_a_clear_message(settings):
    settings.NORA_HOME_LAT = None
    record = Integration.objects.create(slug="weather", name="Weather")

    result = run_integration(record.pk)

    assert result["ok"] is False
    assert "NORA_HOME_LAT" in result["error"]
