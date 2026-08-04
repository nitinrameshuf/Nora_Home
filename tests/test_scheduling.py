"""
Cadences and materialization.

"Occurrences are materialized, not computed" is one of this project's load-bearing
decisions (CLAUDE.md §4). That makes `materialize()` the function that decides
what the house believes is due — and makes its idempotency non-negotiable, since
the sweep re-runs it on a timer forever.

Dates here are fixed rather than relative to today. A cadence test that depends
on which weekday the suite runs is a test that passes six days a week.
"""

from __future__ import annotations

from datetime import date, time, timedelta

import pytest
from django.utils import timezone

from nora_home.tracker.models import Cadence, Occurrence
from nora_home.tracker.scheduling import (
    DEFAULT_DUE_TIME,
    HORIZON_DAYS,
    _clamp_day,
    _window_days,
    due_datetime,
    materialize,
    next_due_dates,
)

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 8, 3)  # a real Monday, checked


# ── cadences ─────────────────────────────────────────────────────────────────

def test_daily_produces_consecutive_days(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.DAILY, starts_on=MONDAY)

    dates = next_due_dates(trackable, MONDAY - timedelta(days=1), count=5)

    assert dates == [MONDAY + timedelta(days=n) for n in range(5)]


def test_weekdays_skips_saturday_and_sunday(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.WEEKDAYS, starts_on=MONDAY)

    dates = next_due_dates(trackable, MONDAY - timedelta(days=1), count=7)

    assert all(d.weekday() < 5 for d in dates)
    assert dates[4] == date(2026, 8, 7)   # Friday
    assert dates[5] == date(2026, 8, 10)  # the next Monday, not Saturday


def test_weekly_repeats_on_the_start_days_weekday(make_trackable, member):
    wednesday = date(2026, 8, 5)
    trackable = make_trackable(member, cadence=Cadence.WEEKLY, starts_on=wednesday)

    dates = next_due_dates(trackable, wednesday - timedelta(days=1), count=3)

    assert dates == [wednesday, date(2026, 8, 12), date(2026, 8, 19)]


def test_monthly_repeats_on_the_same_day_of_month(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.MONTHLY,
                               starts_on=date(2026, 1, 15))

    dates = next_due_dates(trackable, date(2026, 1, 14), count=3)

    assert dates == [date(2026, 1, 15), date(2026, 2, 15), date(2026, 3, 15)]


def test_monthly_on_the_31st_still_fires_in_short_months(make_trackable, member):
    """A quarterly filter change set for the 31st must not silently skip
    February — a maintenance task that vanishes is worse than a late one."""
    trackable = make_trackable(member, cadence=Cadence.MONTHLY,
                               starts_on=date(2026, 1, 31))

    dates = next_due_dates(trackable, date(2026, 1, 30), count=4)

    assert dates[0] == date(2026, 1, 31)
    assert dates[1] == date(2026, 2, 28), "February was skipped instead of clamped"
    assert dates[2] == date(2026, 3, 31)


def test_clamp_day_handles_leap_years():
    assert _clamp_day(31, date(2024, 2, 1)) == 29
    assert _clamp_day(31, date(2026, 2, 1)) == 28
    assert _clamp_day(15, date(2026, 2, 1)) == 15


def test_quarterly_fires_every_third_month(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.QUARTERLY,
                               starts_on=date(2026, 1, 10))

    dates = next_due_dates(trackable, date(2026, 1, 9), count=3)

    assert dates == [date(2026, 1, 10), date(2026, 4, 10), date(2026, 7, 10)]


def test_yearly_fires_on_the_same_month_and_day(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.YEARLY,
                               starts_on=date(2026, 6, 21))

    dates = next_due_dates(trackable, date(2026, 6, 20), count=2)

    assert dates == [date(2026, 6, 21), date(2027, 6, 21)]


def test_interval_counts_from_the_start_date(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.INTERVAL, interval_days=3,
                               starts_on=MONDAY)

    dates = next_due_dates(trackable, MONDAY - timedelta(days=1), count=3)

    assert dates == [MONDAY, MONDAY + timedelta(days=3), MONDAY + timedelta(days=6)]


def test_interval_without_a_value_falls_back_to_daily(make_trackable, member):
    """interval_days is nullable; a null must not mean "never fires again"."""
    trackable = make_trackable(member, cadence=Cadence.INTERVAL, interval_days=None,
                               starts_on=MONDAY)

    assert len(next_due_dates(trackable, MONDAY - timedelta(days=1), count=3)) == 3


def test_once_produces_exactly_one_date(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.ONCE, starts_on=MONDAY)

    assert next_due_dates(trackable, MONDAY - timedelta(days=1)) == [MONDAY]


def test_once_produces_nothing_after_it_has_passed(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.ONCE, starts_on=MONDAY)

    assert next_due_dates(trackable, MONDAY) == []


def test_ends_on_stops_the_series(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.DAILY, starts_on=MONDAY,
                               ends_on=MONDAY + timedelta(days=2))

    dates = next_due_dates(trackable, MONDAY - timedelta(days=1), count=10)

    assert dates == [MONDAY, MONDAY + timedelta(days=1), MONDAY + timedelta(days=2)]


def test_dates_never_start_before_the_trackable_does(make_trackable, member):
    """Creating a habit today must not retroactively make you late for last week."""
    trackable = make_trackable(member, cadence=Cadence.DAILY, starts_on=MONDAY)

    dates = next_due_dates(trackable, MONDAY - timedelta(days=30), count=3)

    assert min(dates) >= MONDAY


def test_an_unknown_cadence_yields_nothing_rather_than_looping(make_trackable, member):
    trackable = make_trackable(member, cadence="fortnightly-ish", starts_on=MONDAY)

    assert next_due_dates(trackable, MONDAY - timedelta(days=1), count=3) == []


def test_a_bad_cron_expression_is_survivable(make_trackable, member):
    """A typo in one trackable's cron must not take down the scheduling sweep
    for every other trackable in the house."""
    trackable = make_trackable(member, cadence=Cadence.CRON,
                               cron_expression="not a cron expression")

    assert next_due_dates(trackable, MONDAY, count=3) == []


# ── due times ────────────────────────────────────────────────────────────────

def test_due_datetime_uses_the_trackables_own_time(make_trackable, member):
    trackable = make_trackable(member, due_time=time(7, 30))

    when = due_datetime(trackable, MONDAY)

    assert timezone.localtime(when).hour == 7
    assert timezone.localtime(when).minute == 30


def test_due_datetime_falls_back_to_the_house_default(make_trackable, member):
    trackable = make_trackable(member, due_time=None)

    when = due_datetime(trackable, MONDAY)

    assert timezone.localtime(when).hour == DEFAULT_DUE_TIME.hour


def test_due_datetime_is_timezone_aware(make_trackable, member):
    """A naive datetime here would compare wrongly against `timezone.now()` in
    the escalation sweep, which is how everything becomes silently overdue."""
    assert timezone.is_aware(due_datetime(make_trackable(member), MONDAY))


# ── materialization ──────────────────────────────────────────────────────────

def test_materialize_creates_occurrences_within_the_horizon(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.DAILY,
                               starts_on=timezone.localdate())

    created = materialize(trackable)

    assert created > 0
    assert trackable.occurrences.count() == created
    latest = trackable.occurrences.order_by("-due_at").first()
    assert timezone.localtime(latest.due_at).date() <= (
        timezone.localdate() + timedelta(days=HORIZON_DAYS))


def test_materialize_is_idempotent(make_trackable, member):
    """The sweep re-runs this forever. A second run must create nothing — this
    is the difference between a stable house and one that doubles its own
    homework every five minutes."""
    trackable = make_trackable(member, cadence=Cadence.DAILY,
                               starts_on=timezone.localdate())
    materialize(trackable)
    count_after_first = trackable.occurrences.count()

    created = materialize(trackable)

    assert created == 0
    assert trackable.occurrences.count() == count_after_first


def test_materialize_sets_next_due_at(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.DAILY,
                               starts_on=timezone.localdate())

    materialize(trackable)

    trackable.refresh_from_db()
    earliest = trackable.occurrences.order_by("due_at").first()
    assert trackable.next_due_at == earliest.due_at


def test_next_due_at_skips_completed_occurrences(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.DAILY,
                               starts_on=timezone.localdate())
    materialize(trackable)
    first = trackable.occurrences.order_by("due_at").first()

    first.complete()
    materialize(trackable)

    trackable.refresh_from_db()
    assert trackable.next_due_at != first.due_at


def test_materialize_skips_inactive_trackables(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.DAILY, is_active=False)

    assert materialize(trackable) == 0
    assert trackable.occurrences.count() == 0


def test_materialize_skips_soft_deleted_trackables(make_trackable, member):
    """A deleted chore that keeps materializing keeps escalating — this is how a
    deleted record haunts the house."""
    trackable = make_trackable(member, cadence=Cadence.DAILY)
    trackable.delete()

    assert materialize(trackable) == 0


def test_materialize_sets_a_window_so_occurrences_can_expire(make_trackable, member):
    trackable = make_trackable(member, cadence=Cadence.DAILY,
                               starts_on=timezone.localdate())

    materialize(trackable)

    for occurrence in trackable.occurrences.all():
        assert occurrence.window_ends_at is not None
        assert occurrence.window_ends_at > occurrence.due_at


@pytest.mark.parametrize("cadence,expected_days", [
    (Cadence.DAILY, 1), (Cadence.WEEKDAYS, 1), (Cadence.WEEKLY, 3),
    (Cadence.MONTHLY, 7), (Cadence.QUARTERLY, 14), (Cadence.YEARLY, 30),
    (Cadence.ONCE, 30),
])
def test_grace_windows_scale_with_the_cadence(make_trackable, member, cadence,
                                              expected_days):
    """A daily habit missed by a day is missed; a yearly one is not. The window
    is what stops the streak maths from being nonsense."""
    assert _window_days(make_trackable(member, cadence=cadence)) == expected_days


def test_the_unique_constraint_stops_duplicate_occurrences(make_trackable, member):
    from django.db import IntegrityError

    trackable = make_trackable(member)
    when = due_datetime(trackable, MONDAY)
    Occurrence.objects.create(trackable=trackable, due_at=when)

    with pytest.raises(IntegrityError):
        Occurrence.objects.create(trackable=trackable, due_at=when)
