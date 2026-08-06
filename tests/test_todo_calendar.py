"""
Month-view calendar math and the page it drives (docs/Main_App/subsystems/
todo.md §6 "Calendar"). The date arithmetic (`nora_home.todo.calendar`) is
tested standalone, with no database, precisely because it's the part most
likely to be subtly wrong at a month or year boundary — the same reasoning
`recurrence.py`'s own tests use.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from nora_home.todo import api
from nora_home.todo.calendar import event_occurs_on, events_by_day, month_weeks, shift_month
from nora_home.todo.models import Event, EventRecurrence, Priority, Task, TaskState
from nora_home.todo.scheduling import current_instance, materialize

pytestmark = pytest.mark.django_db


# ── month_weeks ──────────────────────────────────────────────────────────────

def test_the_grid_covers_the_whole_month():
    weeks = month_weeks(2026, 8)
    days = [d for week in weeks for d in week]

    assert date(2026, 8, 1) in days
    assert date(2026, 8, 31) in days


def test_every_week_is_a_full_monday_starting_week():
    weeks = month_weeks(2026, 8)

    for week in weeks:
        assert len(week) == 7
        assert week[0].weekday() == 0  # Monday
        assert week[-1].weekday() == 6  # Sunday


def test_leading_and_trailing_days_borrow_from_neighbouring_months():
    """August 1st, 2026 is a Saturday — the grid's first row has to reach back
    into July to start on a Monday."""
    weeks = month_weeks(2026, 8)

    assert weeks[0][0] < date(2026, 8, 1)
    assert weeks[0][0].month == 7


def test_february_in_a_leap_year_is_whole():
    weeks = month_weeks(2028, 2)
    days = [d for week in weeks for d in week]

    assert date(2028, 2, 29) in days


def test_december_rolls_into_january_without_a_month_13():
    weeks = month_weeks(2026, 12)
    days = [d for week in weeks for d in week]

    assert date(2027, 1, 1) in days


# ── shift_month ──────────────────────────────────────────────────────────────

def test_shifting_forward_past_december_rolls_the_year():
    assert shift_month(2026, 12, 1) == (2027, 1)


def test_shifting_backward_past_january_rolls_the_year():
    assert shift_month(2026, 1, -1) == (2025, 12)


def test_shifting_by_several_months_at_once():
    assert shift_month(2026, 8, 6) == (2027, 2)


# ── event_occurs_on ──────────────────────────────────────────────────────────

def make_event(**kwargs):
    kwargs.setdefault("title", "An event")
    return Event.objects.create(**kwargs)


def test_a_one_time_event_matches_only_its_own_date():
    event = make_event(starts_at=timezone.make_aware(
        datetime(2026, 3, 14, 9, 0)))

    assert event_occurs_on(event, date(2026, 3, 14))
    assert not event_occurs_on(event, date(2027, 3, 14))


def test_a_yearly_event_recurs_on_the_same_month_and_day_every_year():
    event = make_event(
        starts_at=timezone.make_aware(datetime(2020, 3, 14, 0, 0)),
        recurrence=EventRecurrence.YEARLY)

    assert event_occurs_on(event, date(2026, 3, 14))
    assert event_occurs_on(event, date(2031, 3, 14))
    assert not event_occurs_on(event, date(2026, 3, 15))


def test_a_yearly_event_born_on_leap_day_clamps_into_february_28th():
    event = make_event(
        starts_at=timezone.make_aware(datetime(2020, 2, 29, 0, 0)),
        recurrence=EventRecurrence.YEARLY)

    assert event_occurs_on(event, date(2026, 2, 28))  # not a leap year
    assert event_occurs_on(event, date(2028, 2, 29))  # a leap year


def test_events_by_day_buckets_correctly():
    days = month_weeks(2026, 3)[2]  # some week inside March
    event = make_event(starts_at=timezone.make_aware(
        datetime(2026, 3, 14, 0, 0)))

    buckets = events_by_day(Event.objects.all(), days)

    assert buckets[date(2026, 3, 14)] == [event]
    other_day = next(d for d in days if d != date(2026, 3, 14))
    assert buckets[other_day] == []


# ── the page ─────────────────────────────────────────────────────────────────

@pytest.fixture
def make_task(member):
    def _make(**kwargs):
        kwargs.setdefault("title", "A thing")
        kwargs.setdefault("owner", member)
        kwargs.setdefault("priority", Priority.P2)
        return Task.objects.create(**kwargs)

    return _make


def test_the_calendar_page_renders(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:calendar"))

    assert response.status_code == 200


def test_a_planned_instance_appears_on_its_due_day(client, member, make_task):
    due = timezone.localdate() + timedelta(days=3)
    task = make_task(title="Water the plants", due_on=due)
    materialize(task)
    client.force_login(member)

    response = client.get(reverse("todo:calendar"), {"year": due.year, "month": due.month})

    assert task.title.encode() in response.content


def test_a_completed_instance_shows_as_actual_not_planned(client, member, make_task):
    due = timezone.localdate()
    task = make_task(title="Take out the trash", due_on=due)
    materialize(task)
    client.force_login(member)
    api.complete(current_instance(task), member=member)

    response = client.get(reverse("todo:calendar"))

    assert b"todo-cal__item--actual" in response.content
    assert task.title.encode() in response.content


def test_an_archived_tasks_instance_does_not_appear(client, member, make_task):
    due = timezone.localdate()
    task = make_task(title="Parked chore", due_on=due)
    materialize(task)
    task.state = TaskState.ARCHIVED
    task.save(update_fields=["state"])
    client.force_login(member)

    response = client.get(reverse("todo:calendar"))

    assert task.title.encode() not in response.content


def test_a_shared_tasks_instance_appears_on_an_assignees_calendar(
        client, member, make_member, make_task):
    bob = make_member("bob")
    task = make_task(title="Shared chore", due_on=timezone.localdate(), owner=bob)
    task.assignees.set([member])
    materialize(task)
    client.force_login(member)

    response = client.get(reverse("todo:calendar"))

    assert task.title.encode() in response.content


def test_a_house_wide_event_appears_for_anyone(client, member):
    Event.objects.create(title="Bin day", owner=None,
                         starts_at=timezone.now())

    client.force_login(member)
    response = client.get(reverse("todo:calendar"))

    assert b"Bin day" in response.content


def test_navigating_to_an_invalid_month_falls_back_to_today_rather_than_erroring(
        client, member):
    client.force_login(member)

    response = client.get(reverse("todo:calendar"), {"year": 2026, "month": 13})

    assert response.status_code == 200


def test_prev_and_next_links_are_present_and_shift_by_one_month(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:calendar"), {"year": 2026, "month": 8})

    content = response.content.decode()
    assert "year=2026&amp;month=7" in content or "year=2026&month=7" in content
    assert "year=2026&amp;month=9" in content or "year=2026&month=9" in content


def test_a_rolling_recurrence_marker_appears_on_its_one_open_instance(
        client, member, make_task):
    from nora_home.todo.models import RecurrenceType

    task = make_task(title="Water the succulent",
                     recurrence_type=RecurrenceType.ROLLING,
                     recurrence_spec={"days": 3},
                     due_on=timezone.localdate())
    materialize(task)
    client.force_login(member)

    response = client.get(reverse("todo:calendar"))

    assert task.title.encode() in response.content
