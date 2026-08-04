"""
Shared fixtures for the whole suite.

Everything here is deliberately cheap and hermetic: no network, no Redis, no
Mongo, no MinIO, no Slack. Tests that would otherwise reach outside the process
either use a fake or are skipped with a visible reason — a test that silently
passes because a service was missing is worse than no test.

The suite runs against `config.settings.dev` (see pyproject.toml), which is
SQLite + locmem cache + the in-memory channel layer + eager Celery. That is a
deliberate choice: the tests must run identically on a laptop and on the Pi,
without depending on which containers happen to be up.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from django.core.cache import cache
from django.utils import timezone

from nora_home.accounts.models import EscalationContact, HouseMember
from nora_home.displays.models import Display
from nora_home.notifications.models import Notification
from nora_home.telemetry.models import Series
from nora_home.tracker.models import Cadence, EscalationPolicy, Occurrence, Trackable


# ── hygiene ──────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _clear_cache():
    """The settings store caches in locmem for 300s, which would otherwise leak
    one test's HouseSetting into the next. Clearing around every test is far
    cheaper than debugging the cross-talk."""
    cache.clear()
    yield
    cache.clear()


@pytest.fixture(autouse=True)
def _quiet_channel_layer(settings):
    """Force the in-memory channel layer even if the environment points at Redis,
    so `bus.send_to_display()` and `bot.say()` are exercised for real rather than
    swallowed by a missing-layer warning."""
    settings.CHANNEL_LAYERS = {
        "default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}
    }


# ── people ───────────────────────────────────────────────────────────────────

@pytest.fixture
def make_member(db):
    """Factory. Roles matter more than names in nearly every test here."""
    counter = {"n": 0}

    def _make(username: str = "", *, role: str = HouseMember.Role.MEMBER, **kwargs):
        counter["n"] += 1
        username = username or f"member{counter['n']}"
        kwargs.setdefault("display_name", username.title())
        # Quiet hours default to 22:00–07:00, which silently reroutes every push
        # channel to inapp — so any routing test run late at night would fail for
        # reasons that have nothing to do with the code. Off by default here;
        # tests that are actually about quiet hours set the window themselves.
        kwargs.setdefault("quiet_hours_start", 0)
        kwargs.setdefault("quiet_hours_end", 0)
        return HouseMember.objects.create(username=username, role=role, **kwargs)

    return _make


@pytest.fixture
def member(make_member):
    return make_member("kid", role=HouseMember.Role.MEMBER)


@pytest.fixture
def adult(make_member):
    return make_member("parent", role=HouseMember.Role.ADULT)


@pytest.fixture
def admin_member(make_member):
    return make_member("nitin", role=HouseMember.Role.ADMIN)


@pytest.fixture
def household(make_member):
    """A realistic house: one admin, one adult, one kid, with a chain set up."""
    boss = make_member("nitin", role=HouseMember.Role.ADMIN)
    partner = make_member("partner", role=HouseMember.Role.ADULT)
    kid = make_member("kid", role=HouseMember.Role.MEMBER)
    EscalationContact.objects.create(member=kid, contact=partner, level=1)
    EscalationContact.objects.create(member=kid, contact=boss, level=2)
    return {"admin": boss, "adult": partner, "kid": kid}


# ── tracker ──────────────────────────────────────────────────────────────────

@pytest.fixture
def policy(db):
    """A four-rung ladder with no grace, so tests control timing precisely."""
    return EscalationPolicy.objects.create(
        name="Test ladder",
        grace_minutes=0,
        levels=[
            {"after_minutes": 0, "notify": "owner", "severity": "nudge"},
            {"after_minutes": 60, "notify": "owner", "severity": "warning"},
            {"after_minutes": 120, "notify": "chain", "severity": "alert"},
            {"after_minutes": 240, "notify": "house", "severity": "critical"},
        ],
    )


@pytest.fixture
def make_trackable(db, policy):
    def _make(owner, *, title="Test thing", cadence=Cadence.DAILY, **kwargs):
        kwargs.setdefault("app_slug", "tracker")
        kwargs.setdefault("starts_on", timezone.localdate())
        kwargs.setdefault("due_time", time(18, 0))
        kwargs.setdefault("escalation_policy", policy)
        return Trackable.objects.create(
            owner=owner, title=title, cadence=cadence, **kwargs)

    return _make


@pytest.fixture
def make_occurrence(db):
    """An occurrence at a chosen age. `minutes_overdue` is the knob nearly every
    escalation test wants to turn."""
    def _make(trackable, *, minutes_overdue: int = 0, **kwargs):
        due = timezone.now() - timedelta(minutes=minutes_overdue)
        kwargs.setdefault("window_ends_at", due + timedelta(days=1))
        return Occurrence.objects.create(trackable=trackable, due_at=due, **kwargs)

    return _make


# ── other subsystems ─────────────────────────────────────────────────────────

@pytest.fixture
def series(db):
    return Series.objects.create(
        key="test.metric", label="Test metric", unit="u",
        warn_below=10, alert_below=5, warn_above=90, alert_above=95,
    )


@pytest.fixture
def wall_display(db):
    return Display.objects.create(slug="wall", name="Wall", kind=Display.Kind.WALL)


@pytest.fixture
def kiosk_display(db):
    return Display.objects.create(slug="kiosk", name="Kiosk", kind=Display.Kind.KIOSK)


@pytest.fixture
def captured_notifications(db):
    """Notifications are written to the DB before any channel runs, so asserting
    on the table is both simpler and more faithful than mocking the channels."""
    class _Captured:
        @staticmethod
        def all():
            return list(Notification.objects.order_by("created_at"))

        @staticmethod
        def titles():
            return [n.title for n in Notification.objects.order_by("created_at")]

        @staticmethod
        def count():
            return Notification.objects.count()

    return _Captured()


@pytest.fixture
def signal_recorder():
    """Collect signal fires without leaving receivers connected afterwards."""
    connected = []

    class _Recorder:
        def __init__(self):
            self.calls = []

        def watch(self, signal):
            def receiver(sender, **kwargs):
                self.calls.append(kwargs)
            signal.connect(receiver, weak=False)
            connected.append((signal, receiver))
            return self

    recorder = _Recorder()
    yield recorder
    for signal, receiver in connected:
        signal.disconnect(receiver)


@pytest.fixture
def today():
    return timezone.localdate()


@pytest.fixture
def a_monday():
    """A fixed Monday, so weekday-sensitive cadence tests never depend on when
    the suite happens to run."""
    return date(2026, 8, 3)
