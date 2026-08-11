"""
The House log — nora_home/core/houselog.py.

The thing worth testing here is not that rows come back; it is the editorial
rule the module is built on: **record what changed, not what ran.** Most of
these assert that a source *stays quiet*, because that is the behaviour that
makes the page readable and the behaviour a well-meaning change would undo.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from nora_home.core import houselog
from nora_home.core.audit import record
from nora_home.core.models import SystemHealthSnapshot
from nora_home.integrations.models import Integration, IntegrationRun
from nora_home.notifications.models import Delivery, Notification
from nora_home.telemetry.api import define_series, record_reading

pytestmark = pytest.mark.django_db


def _ago(minutes: int):
    return timezone.now() - timedelta(minutes=minutes)


# ── the editorial rule ───────────────────────────────────────────────────────

def test_a_run_of_healthy_snapshots_is_not_a_timeline():
    """563 snapshots in seven days, all healthy, was the real measurement on the
    Pi. Every one of them on the page would bury everything else."""
    for n in range(20):
        SystemHealthSnapshot.objects.create(healthy=True, created_at=_ago(n * 10))

    assert houselog.timeline(sources=["health"]) == []


def test_health_reports_the_moment_it_changed_and_the_moment_it_came_back():
    SystemHealthSnapshot.objects.create(healthy=True, created_at=_ago(50))
    SystemHealthSnapshot.objects.create(
        healthy=False, created_at=_ago(40),
        services={"mysql": {"status": "down"}, "redis": {"status": "ok"}})
    SystemHealthSnapshot.objects.create(healthy=False, created_at=_ago(30))
    SystemHealthSnapshot.objects.create(healthy=True, created_at=_ago(20))

    entries = houselog.timeline(sources=["health"])

    assert [e.title for e in entries] == ["The house recovered",
                                          "The house went degraded"]
    # Which service actually broke, not just that something did.
    assert entries[1].detail == "mysql"
    assert entries[1].severity == "alert"


def test_a_transition_at_the_very_start_of_the_window_is_still_a_transition():
    """The snapshot before the window is what makes the first one inside it
    readable as a change. Without that lookback the house looks like it booted
    degraded every time someone narrows the filter."""
    SystemHealthSnapshot.objects.create(healthy=True, created_at=_ago(400))
    SystemHealthSnapshot.objects.create(healthy=False, created_at=_ago(100))

    entries = houselog.timeline(since=_ago(120), sources=["health"])

    assert [e.title for e in entries] == ["The house went degraded"]


def test_successful_integration_runs_are_not_events():
    integration = Integration.objects.create(slug="weather", name="Weather")
    for n in range(10):
        IntegrationRun.objects.create(integration=integration, succeeded=True,
                                      created_at=_ago(n * 15))

    assert houselog.timeline(sources=["integrations"]) == []


def test_an_integration_failing_all_week_is_one_entry_not_six_hundred():
    integration = Integration.objects.create(slug="weather", name="Weather")
    for n in range(30):
        IntegrationRun.objects.create(integration=integration, succeeded=False,
                                      error="timeout", created_at=_ago(200 - n))

    entries = houselog.timeline(sources=["integrations"])

    assert len(entries) == 1
    assert entries[0].title == "Weather started failing"
    assert entries[0].detail == "timeout"


def test_the_first_success_after_a_failure_is_the_recovery():
    integration = Integration.objects.create(slug="weather", name="Weather")
    IntegrationRun.objects.create(integration=integration, succeeded=False,
                                  error="timeout", created_at=_ago(60))
    IntegrationRun.objects.create(integration=integration, succeeded=True,
                                  duration_ms=140, created_at=_ago(30))
    IntegrationRun.objects.create(integration=integration, succeeded=True,
                                  created_at=_ago(15))

    entries = houselog.timeline(sources=["integrations"])

    assert [e.title for e in entries] == ["Weather recovered",
                                          "Weather started failing"]


def test_two_integrations_failing_are_tracked_apart():
    """Episode state is per integration. Sharing it would let one recovering
    swallow the other's failure."""
    weather = Integration.objects.create(slug="weather", name="Weather")
    stocks = Integration.objects.create(slug="stocks", name="Stocks")
    IntegrationRun.objects.create(integration=weather, succeeded=False, created_at=_ago(60))
    IntegrationRun.objects.create(integration=stocks, succeeded=False, created_at=_ago(50))
    IntegrationRun.objects.create(integration=weather, succeeded=True, created_at=_ago(40))

    titles = {e.title for e in houselog.timeline(sources=["integrations"])}

    assert titles == {"Weather started failing", "Stocks started failing",
                      "Weather recovered"}


def test_a_delivery_that_worked_is_not_something_that_happened(member):
    notification = Notification.objects.create(title="Bins", app_slug="todo",
                                               recipient=member)
    Delivery.objects.create(notification=notification, channel="slack",
                            status=Delivery.Status.SENT)

    assert houselog.timeline(sources=["deliveries"]) == []


def test_a_failed_delivery_and_a_skipped_one_do_not_look_alike(member):
    notification = Notification.objects.create(title="Bins", app_slug="todo",
                                               recipient=member)
    Delivery.objects.create(notification=notification, channel="slack",
                            status=Delivery.Status.FAILED, error="channel_not_found")
    Delivery.objects.create(notification=notification, channel="display",
                            status=Delivery.Status.SKIPPED)

    by_channel = {e.title.split()[0]: e for e in houselog.timeline(sources=["deliveries"])}

    assert by_channel["slack"].severity == "alert"
    assert by_channel["slack"].detail == "channel_not_found"
    assert by_channel["display"].severity == "notice"


# ── the other sources ────────────────────────────────────────────────────────

def test_every_audit_row_is_an_event(adult):
    record("todo", "task.created", actor=adult, subject="Bins")

    entries = houselog.timeline(sources=["audit"])

    assert len(entries) == 1
    assert entries[0].title == "Bins"
    assert entries[0].detail == "task.created"   # the action stays visible
    assert entries[0].actor == adult.name


def test_an_audit_row_with_no_subject_still_reads(adult):
    """record() does not require a subject, so the action has to carry the row
    on its own rather than rendering as a blank line."""
    record("core", "app.installed", actor=adult)

    assert houselog.timeline(sources=["audit"])[0].title == "app.installed"


def test_a_house_wide_notification_says_everyone_rather_than_nothing():
    Notification.objects.create(title="Backup failed", app_slug="data",
                                severity="alert")

    assert houselog.timeline(sources=["notifications"])[0].actor == "everyone"


def test_a_reading_inside_its_thresholds_is_not_an_event():
    define_series("house.temp", "Living room", unit="C", warn_above=30)
    record_reading("house.temp", 21.0)

    assert houselog.timeline(sources=["telemetry"]) == []


def test_a_reading_that_crossed_a_threshold_is():
    define_series("house.temp", "Living room", unit="C", warn_above=30,
                  alert_above=40)
    record_reading("house.temp", 44.0)

    entries = houselog.timeline(sources=["telemetry"])

    assert len(entries) == 1
    assert entries[0].severity == "alert"
    assert "44" in entries[0].title


# ── merging and filtering ────────────────────────────────────────────────────

def test_sources_merge_into_one_timeline_newest_first(adult):
    record("todo", "task.created", actor=adult, subject="Older")
    Notification.objects.create(title="Newer", app_slug="todo")

    entries = houselog.timeline()

    assert [e.title for e in entries] == ["Newer", "Older"]
    assert {e.source for e in entries} == {"audit", "notifications"}


def test_severity_filters_from_a_floor_upwards(adult):
    record("todo", "quiet", actor=adult, subject="quiet", severity="info")
    record("todo", "loud", actor=adult, subject="loud", severity="alert")

    titles = [e.title for e in houselog.timeline(severity="warning")]

    assert titles == ["loud"]


def test_an_unknown_severity_shows_everything_rather_than_nothing():
    """A hand-edited query string must not silently empty the page."""
    assert houselog.severity_at_least("banana") == houselog.SEVERITY_ORDER


def test_the_text_filter_looks_at_the_detail_too(adult):
    record("todo", "task.created", actor=adult, subject="Bins")
    record("todo", "unrelated.thing", actor=adult, subject="Something else")

    assert len(houselog.timeline(query="task.created")) == 1


def test_choosing_a_source_excludes_the_others(adult):
    record("todo", "task.created", actor=adult, subject="Audited")
    Notification.objects.create(title="Notified", app_slug="todo")

    assert [e.title for e in houselog.timeline(sources=["audit"])] == ["Audited"]


def test_entries_outside_the_window_are_not_included(adult):
    old = record("todo", "task.created", actor=adult, subject="Ancient")
    # created_at has a default rather than auto_now_add, so it is writable —
    # which is the only way to test a window without freezing the clock.
    old.created_at = _ago(60 * 24 * 90)
    old.save(update_fields=["created_at"])

    assert houselog.timeline(since=_ago(60 * 24 * 7)) == []


def test_one_broken_source_does_not_take_the_page_down(adult, monkeypatch):
    """CLAUDE.md §6: failures degrade, never cascade. This page is the one
    someone opens *because* something is wrong."""
    record("todo", "task.created", actor=adult, subject="Still here")

    def explode(*args, **kwargs):
        raise RuntimeError("telemetry is on fire")

    monkeypatch.setattr(houselog, "_telemetry_entries", explode)

    assert [e.title for e in houselog.timeline()] == ["Still here"]


def test_the_limit_is_applied_after_merging_not_per_source(adult):
    """Ten of each and a limit of five must give the five newest overall, not
    five of one kind."""
    for n in range(10):
        Notification.objects.create(title=f"n{n}", app_slug="todo")
    for n in range(10):
        record("todo", "task.created", actor=adult, subject=f"a{n}")

    entries = houselog.timeline(limit=5)

    assert len(entries) == 5
    assert entries == sorted(entries, key=lambda e: e.at, reverse=True)


# ── charts ───────────────────────────────────────────────────────────────────

def test_charts_are_none_when_there_is_nothing_to_draw():
    """§10's rule, shared with Reporting: empty is a sentence, never an axis."""
    options = houselog.charts([], since=_ago(60), until=timezone.now())

    assert options == {"activity": None, "mix": None}


def test_the_severity_chart_reads_as_a_ladder_not_a_ranking(adult):
    record("todo", "a", actor=adult, subject="a", severity="alert")
    record("todo", "b", actor=adult, subject="b", severity="info")
    record("todo", "c", actor=adult, subject="c", severity="info")

    entries = houselog.timeline()
    options = houselog.charts(entries, since=_ago(60), until=timezone.now())

    # info before alert, though alert is rarer — sorting by count would make the
    # same chart mean something different on a quiet week.
    assert options["mix"]["xAxis"]["data"] == ["info", "alert"]
    assert options["mix"]["series"][0]["data"] == [2, 1]


def test_the_activity_chart_only_stacks_sources_that_appeared(adult):
    record("todo", "task.created", actor=adult, subject="Bins")

    options = houselog.charts(houselog.timeline(), since=_ago(60),
                              until=timezone.now())

    assert [s["name"] for s in options["activity"]["series"]] == ["Actions"]


# ── the page — merged into System, Story 47 ───────────────────────────────────

def test_the_page_renders(client, admin_member):
    """/home/log/ redirects; the actual page is System's Log tab now
    (Story 55 gave System four tabs — Health is the default, so Timeline only
    renders when asked for explicitly)."""
    client.force_login(admin_member)

    response = client.get(reverse("core:system_status"), {"tab": "log"})

    assert response.status_code == 200
    assert "Timeline" in response.content.decode()


def test_a_skipped_service_gets_the_same_badge_treatment_as_the_others(
        client, admin_member, monkeypatch):
    """Skipped/unknown used to fall back to a bare <span class="lab"> — a
    different, dimmer chip than the .badge every ok/warn/crit status gets, so
    the third state (of collect_health()'s three: ok, down, skipped) read as
    an afterthought rather than a real answer."""
    import nora_home.core.health as health_module

    monkeypatch.setitem(health_module.PROBES, "database",
                        lambda: {"status": "skipped", "reason": "test"})
    client.force_login(admin_member)

    body = client.get(reverse("core:system_status")).content.decode()

    assert '<span class="badge ">skipped</span>' in body
    assert '<span class="lab">skipped</span>' not in body


def test_the_page_survives_a_hand_edited_query_string(client, admin_member):
    client.force_login(admin_member)

    response = client.get(reverse("core:system_status"),
                          {"tab": "log", "days": "nonsense", "severity": "banana",
                           "source": "no-such-source"})

    assert response.status_code == 200
    assert response.context["days"] == houselog.DEFAULT_DAYS
    assert response.context["chosen_sources"] == []


def test_an_unknown_tab_falls_back_to_health(client, admin_member):
    client.force_login(admin_member)

    response = client.get(reverse("core:system_status"), {"tab": "nonsense"})

    assert response.status_code == 200
    assert response.context["tab"] == "health"


def test_the_page_needs_a_signed_in_member(client):
    response = client.get(reverse("core:system_status"))

    assert response.status_code == 302


def test_the_old_url_redirects_there_with_its_query_string(client, admin_member):
    client.force_login(admin_member)

    response = client.get(reverse("core:house_log"), {"days": "30"})

    assert response.status_code == 302
    assert response["Location"] == reverse("core:system_status") + "?days=30&tab=log"
