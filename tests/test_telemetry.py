"""
Telemetry: one time-series store for every number in the house.

The interesting logic is thresholds. A series that never fires its threshold is
a chart nobody looks at; one that fires constantly is noise people learn to
ignore. Both failure modes are asserted against.
"""

from __future__ import annotations

import pytest

from nora_home.core.signals import threshold_crossed
from nora_home.notifications.models import Notification
from nora_home.telemetry.api import define_series, record_reading, series_history
from nora_home.telemetry.models import Reading, Series

pytestmark = pytest.mark.django_db


# ── defining and recording ───────────────────────────────────────────────────

def test_define_series_stores_the_thresholds():
    series = define_series("nora.battery", "Nora battery", unit="%",
                           app_slug="robot", alert_below=15, direction="up")

    assert series.unit == "%"
    assert series.alert_below == 15
    assert series.direction == "up"


def test_defining_the_same_key_twice_updates_it():
    """Called from app startup, so it must be safe to run on every boot."""
    define_series("nora.battery", "Battery", alert_below=15)
    define_series("nora.battery", "Nora battery", alert_below=20)

    assert Series.objects.filter(key="nora.battery").count() == 1
    assert Series.objects.get().alert_below == 20


def test_recording_creates_the_series_on_first_use():
    """A quick experiment should not need a migration — that is the documented
    promise in the module docstring."""
    reading = record_reading("kitchen.temp", 21.5, app_slug="house")

    assert Series.objects.filter(key="kitchen.temp").exists()
    assert reading.value == 21.5


def test_an_auto_created_series_gets_a_readable_label():
    record_reading("kitchen.temp", 20.0)

    assert Series.objects.get().label == "Kitchen Temp"


def test_recording_does_not_clobber_an_explicit_definition():
    """Auto-creation must never overwrite thresholds someone deliberately set."""
    define_series("nora.battery", "Nora battery", unit="%", alert_below=15)

    record_reading("nora.battery", 80.0)

    series = Series.objects.get(key="nora.battery")
    assert series.alert_below == 15
    assert series.label == "Nora battery"


def test_tags_ride_along_with_a_reading():
    reading = record_reading("kitchen.temp", 21.5, room="kitchen", sensor="a1")

    assert reading.tags == {"room": "kitchen", "sensor": "a1"}


def test_values_are_coerced_to_float():
    assert record_reading("x", "21.5").value == 21.5


def test_latest_value_returns_the_most_recent(series):
    record_reading(series.key, 50.0)
    record_reading(series.key, 60.0)

    assert series.latest_value() == 60.0


def test_latest_value_is_none_with_no_readings(series):
    assert series.latest_value() is None


# ── classification ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (50, "ok"),
    (9, "warning"),    # below warn_below (10)
    (4, "alert"),      # below alert_below (5)
    (91, "warning"),   # above warn_above (90)
    (96, "alert"),     # above alert_above (95)
    (10, "ok"),        # exactly on the boundary is not yet a warning
    (90, "ok"),
])
def test_classify_maps_values_to_severity(series, value, expected):
    assert series.classify(value) == expected


def test_alert_wins_over_warning(series):
    """Both bounds are crossed at 4; reporting it as merely a warning would
    understate it."""
    assert series.classify(4) == "alert"


def test_a_series_with_no_thresholds_is_always_ok(db):
    plain = Series.objects.create(key="plain", label="Plain")

    assert plain.classify(-9999) == "ok"
    assert plain.classify(9999) == "ok"


# ── threshold notifications ──────────────────────────────────────────────────

def test_crossing_a_threshold_fires_the_signal(series, signal_recorder):
    signal_recorder.watch(threshold_crossed)

    record_reading(series.key, 2.0)

    assert len(signal_recorder.calls) == 1
    assert signal_recorder.calls[0]["threshold"] == "alert"
    assert signal_recorder.calls[0]["direction"] == "below"


def test_staying_in_range_fires_nothing(series, signal_recorder):
    signal_recorder.watch(threshold_crossed)

    record_reading(series.key, 50.0)

    assert signal_recorder.calls == []
    assert Notification.objects.count() == 0


def test_a_house_series_notifies_the_whole_house(series):
    record_reading(series.key, 2.0)

    notification = Notification.objects.get()
    assert notification.recipient is None
    assert notification.severity == "alert"


def test_a_personal_series_notifies_only_its_owner(db, member):
    series = Series.objects.create(key="body.weight", label="Weight",
                                   member=member, alert_above=100)

    record_reading(series.key, 120.0)

    assert Notification.objects.get().recipient == member


def test_repeated_bad_readings_do_not_spam(series):
    """A sensor stuck below its threshold would otherwise notify on every single
    reading — which is exactly how people learn to ignore alerts."""
    for _ in range(5):
        record_reading(series.key, 2.0)

    assert Notification.objects.count() == 1


def test_direction_is_reported_correctly_for_a_high_reading(series,
                                                            signal_recorder):
    signal_recorder.watch(threshold_crossed)

    record_reading(series.key, 99.0)

    assert signal_recorder.calls[0]["direction"] == "above"


# ── history ──────────────────────────────────────────────────────────────────

def test_series_history_returns_readings_oldest_first(series):
    record_reading(series.key, 50.0)
    record_reading(series.key, 51.0)
    record_reading(series.key, 52.0)

    history = list(series_history(series.key))

    assert [r.value for r in history] == [50.0, 51.0, 52.0]


def test_series_history_excludes_readings_outside_the_window(series):
    from django.utils import timezone

    record_reading(series.key, 50.0)
    Reading.objects.update(recorded_at=timezone.now() - timezone.timedelta(days=5))
    record_reading(series.key, 60.0)

    assert [r.value for r in series_history(series.key, hours=24)] == [60.0]


def test_series_history_for_an_unknown_key_is_empty():
    assert list(series_history("nothing.here")) == []


# ── latest_value ──────────────────────────────────────────────────────────────

def test_latest_value_returns_the_newest_reading():
    from nora_home.telemetry.api import latest_value

    record_reading("pi.cpu_percent", 10.0)
    record_reading("pi.cpu_percent", 20.0)

    assert latest_value("pi.cpu_percent") == 20.0


def test_latest_value_for_an_unrecorded_series_is_none():
    from nora_home.telemetry.api import latest_value

    assert latest_value("nothing.here") is None


# ── Pi vitals (Story 52) ─────────────────────────────────────────────────────

def test_collect_vitals_records_whatever_the_probes_return(monkeypatch):
    """A dev laptop has no fan tacho and no vcgencmd — those two must be
    skipped, not raise, and the rest must still be recorded (CLAUDE.md §6,
    failures degrade)."""
    from nora_home.telemetry import probes, tasks

    monkeypatch.setattr(probes, "read_cpu_percent", lambda: 12.5)
    monkeypatch.setattr(probes, "read_memory_percent", lambda: 33.0)
    monkeypatch.setattr(probes, "read_load_average", lambda: 0.8)
    monkeypatch.setattr(probes, "read_uptime_hours", lambda: 100.0)
    monkeypatch.setattr(probes, "read_fan_rpm", lambda: None)
    monkeypatch.setattr(probes, "read_throttled", lambda: None)

    result = tasks.collect_vitals()

    assert set(result["recorded"]) == {
        "pi.cpu_percent", "pi.memory_percent", "pi.load_average", "pi.uptime_hours",
    }
    assert Series.objects.get(key="pi.cpu_percent").latest_value() == 12.5
    assert not Series.objects.filter(key="pi.fan_rpm").exists()


def test_a_broken_probe_does_not_block_the_others(monkeypatch):
    from nora_home.telemetry import probes, tasks

    def explode():
        raise OSError("no such file")

    monkeypatch.setattr(probes, "read_cpu_percent", explode)
    monkeypatch.setattr(probes, "read_memory_percent", lambda: 50.0)
    monkeypatch.setattr(probes, "read_load_average", lambda: None)
    monkeypatch.setattr(probes, "read_uptime_hours", lambda: None)
    monkeypatch.setattr(probes, "read_fan_rpm", lambda: None)
    monkeypatch.setattr(probes, "read_throttled", lambda: None)

    result = tasks.collect_vitals()

    assert result["recorded"] == ["pi.memory_percent"]


def test_throttled_flags_being_set_is_an_alert(monkeypatch):
    """Bit 0 is under-voltage happening right now — the single most valuable
    Pi signal here, and it has no /proc or /sys equivalent."""
    from nora_home.telemetry import probes, tasks

    monkeypatch.setattr(probes, "read_cpu_percent", lambda: None)
    monkeypatch.setattr(probes, "read_memory_percent", lambda: None)
    monkeypatch.setattr(probes, "read_load_average", lambda: None)
    monkeypatch.setattr(probes, "read_uptime_hours", lambda: None)
    monkeypatch.setattr(probes, "read_fan_rpm", lambda: None)
    monkeypatch.setattr(probes, "read_throttled", lambda: 0x50001)  # under-voltage now

    tasks.collect_vitals()

    series = Series.objects.get(key="pi.throttled")
    assert series.classify(0x50001) == "alert"


def test_cpu_percent_is_read_as_a_rate_not_a_running_total():
    """A single /proc/stat read is jiffies since boot; the probe must sample
    twice and diff, or the number would only ever grow."""
    from nora_home.telemetry.probes import read_cpu_percent

    value = read_cpu_percent(interval=0.05)

    if value is None:
        pytest.skip("no /proc/stat here (not Linux)")
    assert 0 <= value <= 100
