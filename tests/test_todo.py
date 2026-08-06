"""
Todo — recurrence, materialisation, and how an occasion closes.

This is the correctness core of the subsystem: everything downstream (the
board, reminders, every chart on the Reporting page) reads the instances these
functions write. A rule that is subtly wrong here is wrong everywhere, and
quietly — which is why this file leans on fixed dates rather than "now", and
asserts the shape of the whole instance set rather than just the next one.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.utils import IntegrityError
from django.utils import timezone

from nora_home.core.signals import item_completed
from nora_home.todo import api
from nora_home.todo.models import (
    Instance,
    InstanceOutcome,
    Priority,
    RecurrenceType,
    Task,
    TaskState,
    TodoPreference,
)
from nora_home.todo.recurrence import (
    anchor_date,
    due_at_on,
    due_time_for,
    falls_due_on,
    fixed_dates,
    next_rolling_due,
)
from nora_home.todo.scheduling import (
    HORIZON_DAYS,
    close_passed_instances,
    current_instance,
    materialize,
    materialize_open_tasks,
)

pytestmark = pytest.mark.django_db

MONDAY = date(2026, 8, 3)  # a real Monday, so weekday tests never drift


@pytest.fixture
def make_task(member):
    def _make(**kwargs):
        kwargs.setdefault("title", "A thing")
        kwargs.setdefault("owner", member)
        kwargs.setdefault("priority", Priority.P2)
        return Task.objects.create(**kwargs)

    return _make


@pytest.fixture
def daily_with_history(make_task):
    """A daily task that already has `days` past occasions, all still open.

    The instances are written directly rather than materialised, because
    materialisation deliberately never backfills (see `_materialize_fixed`) —
    this is what the same task looks like after running for a week with nobody
    touching it, which is the state the closing rule exists to resolve. Every
    due moment is strictly in the past regardless of what time the suite runs,
    so the assertions never depend on the clock.
    """
    def _make(days: int, **kwargs):
        task = make_task(recurrence_type=RecurrenceType.FIXED,
                         recurrence_spec={"kind": "daily"},
                         due_on=timezone.localdate() - timedelta(days=days), **kwargs)
        base = timezone.now() - timedelta(minutes=1)
        for back in range(days, -1, -1):
            Instance.objects.create(task=task, due_at=base - timedelta(days=back))
        return task

    return _make


def _local(when):
    return timezone.localtime(when)


def _days(task):
    """Every instance's local due date, in order — the shape assertions read
    much better against this than against datetimes."""
    return [_local(i.due_at).date() for i in task.instances.order_by("due_at")]


# ── when something falls due ─────────────────────────────────────────────────

def test_a_task_with_a_due_date_anchors_on_it(make_task):
    task = make_task(due_on=MONDAY)

    assert anchor_date(task) == MONDAY


def test_a_task_with_no_due_date_anchors_on_when_it_was_created(make_task):
    """A recurring task with no due date still has to start somewhere, or it
    silently produces nothing at all."""
    task = make_task()

    assert anchor_date(task) == _local(task.created_at).date()


def test_the_due_time_is_the_tasks_own_when_it_has_one(make_task):
    task = make_task(due_time=time(7, 30))

    assert due_time_for(task) == time(7, 30)


def test_a_date_only_task_falls_due_at_the_members_preferred_hour(make_task, member):
    """§8 — a date with no time means "that day", and which hour that lands on
    is the owner's preference, not a constant."""
    TodoPreference.objects.create(member=member, default_due_hour=6)
    task = make_task(due_on=MONDAY)

    assert due_time_for(task) == time(6, 0)


def test_a_date_only_task_falls_back_to_nine_when_nobody_set_a_preference(make_task):
    task = make_task(due_on=MONDAY)

    assert due_time_for(task) == time(9, 0)


def test_the_due_moment_is_built_in_the_houses_timezone(make_task):
    task = make_task(due_on=MONDAY, due_time=time(9, 0))

    when = due_at_on(task, MONDAY)

    assert _local(when).date() == MONDAY
    assert _local(when).hour == 9


# ── fixed recurrence ─────────────────────────────────────────────────────────

def test_daily_falls_due_every_day(make_task):
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})

    dates = fixed_dates(task, after=MONDAY, until=MONDAY + timedelta(days=5))

    assert dates == [MONDAY + timedelta(days=n) for n in range(1, 6)]


def test_weekdays_skips_the_weekend(make_task):
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "weekdays"})

    dates = fixed_dates(task, after=MONDAY, until=MONDAY + timedelta(days=7))

    weekdays = {d.weekday() for d in dates}
    assert weekdays <= {0, 1, 2, 3, 4}, "a weekday rule produced a Saturday or Sunday"
    assert MONDAY + timedelta(days=5) not in dates  # the Saturday


def test_weekly_with_no_explicit_days_repeats_on_the_anchors_weekday(make_task):
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "weekly"})

    dates = fixed_dates(task, after=MONDAY, until=MONDAY + timedelta(days=21))

    assert dates == [MONDAY + timedelta(days=7),
                     MONDAY + timedelta(days=14),
                     MONDAY + timedelta(days=21)]


def test_weekly_can_name_several_days(make_task):
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "weekly", "weekdays": [0, 2]})

    dates = fixed_dates(task, after=MONDAY, until=MONDAY + timedelta(days=13))

    assert {d.weekday() for d in dates} == {0, 2}


def test_monthly_clamps_into_short_months(make_task):
    """The 31st of February is the 28th. Without clamping a monthly chore
    silently skips five months a year — the failure nobody notices until they
    look back at a whole year of history."""
    task = make_task(due_on=date(2026, 1, 31), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "monthly", "day": 31})

    dates = fixed_dates(task, after=date(2026, 1, 31), until=date(2026, 4, 30))

    assert date(2026, 2, 28) in dates, "February was skipped entirely"
    assert date(2026, 3, 31) in dates
    assert date(2026, 4, 30) in dates, "April (30 days) was skipped"


def test_monthly_in_a_leap_february(make_task):
    task = make_task(due_on=date(2028, 1, 31), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "monthly", "day": 31})

    dates = fixed_dates(task, after=date(2028, 1, 31), until=date(2028, 2, 29))

    assert dates == [date(2028, 2, 29)]


def test_yearly_repeats_on_the_same_calendar_day(make_task):
    task = make_task(due_on=date(2026, 3, 14), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "yearly"})

    dates = fixed_dates(task, after=date(2026, 3, 14), until=date(2028, 1, 1))

    assert dates == [date(2027, 3, 14)]


def test_interval_counts_from_the_anchor(make_task):
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "interval", "days": 3})

    dates = fixed_dates(task, after=MONDAY, until=MONDAY + timedelta(days=9))

    assert dates == [MONDAY + timedelta(days=3),
                     MONDAY + timedelta(days=6),
                     MONDAY + timedelta(days=9)]


def test_nothing_falls_due_before_the_anchor(make_task):
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})

    assert falls_due_on(task, MONDAY - timedelta(days=1)) is False


def test_a_rule_stops_at_its_end_date(make_task):
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily",
                                      "ends_on": (MONDAY + timedelta(days=3)).isoformat()})

    dates = fixed_dates(task, after=MONDAY, until=MONDAY + timedelta(days=30))

    assert dates == [MONDAY + timedelta(days=1),
                     MONDAY + timedelta(days=2),
                     MONDAY + timedelta(days=3)]


@pytest.mark.parametrize("spec", [
    {},
    {"kind": "nonsense"},
    {"kind": "interval", "days": 0},
    {"kind": "interval", "days": -5},
])
def test_an_unusable_rule_produces_nothing_rather_than_raising(make_task, spec):
    """A spec someone typed by hand in the admin should cost that one task its
    schedule, not crash the nightly job for the whole house."""
    task = make_task(due_on=MONDAY, recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec=spec)

    assert fixed_dates(task, after=MONDAY, until=MONDAY + timedelta(days=30)) == []


# ── materialisation: one-shot ────────────────────────────────────────────────

def test_a_one_shot_task_gets_exactly_one_instance(make_task):
    task = make_task(due_on=MONDAY)

    assert materialize(task) == 1
    assert _days(task) == [MONDAY]


def test_materialising_twice_does_not_duplicate(make_task):
    task = make_task(due_on=MONDAY)
    materialize(task)

    assert materialize(task) == 0
    assert task.instances.count() == 1


def test_a_task_with_no_due_date_gets_no_instance(make_task):
    """An instance's due_at is the moment it was *for*. Inventing one would put
    a fabricated date into the history every chart is drawn from."""
    task = make_task()

    assert materialize(task) == 0
    assert task.instances.count() == 0


def test_rescheduling_a_one_shot_moves_its_instance_rather_than_adding_one(make_task):
    task = make_task(due_on=MONDAY)
    materialize(task)

    task.due_on = MONDAY + timedelta(days=2)
    task.save()
    materialize(task)

    assert _days(task) == [MONDAY + timedelta(days=2)]


def test_a_completed_one_shot_does_not_sprout_a_new_instance(make_task):
    """The bug this guards against would make "done" never stay done: every
    nightly run would hand the task a fresh open occasion."""
    task = make_task(due_on=MONDAY)
    materialize(task)
    task.instances.update(outcome=InstanceOutcome.DONE, completed_at=timezone.now())

    assert materialize(task) == 0
    assert task.instances.count() == 1


# ── materialisation: fixed ───────────────────────────────────────────────────

def test_a_fixed_recurrence_fills_the_horizon(make_task):
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})

    materialize(task)

    days = _days(task)
    assert len(days) >= HORIZON_DAYS - 1, "the 90-day window was not filled"
    assert max(days) <= timezone.localdate() + timedelta(days=HORIZON_DAYS)


def test_materialising_a_fixed_recurrence_again_creates_nothing_new(make_task):
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})
    first = materialize(task)

    assert first > 0
    assert materialize(task) == 0


def test_changing_the_rule_drops_the_future_instances_it_no_longer_produces(make_task):
    """Changing "every Monday" to "every Tuesday" must not leave 13 phantom
    Mondays sitting on the calendar forever."""
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "weekly", "weekdays": [0]})
    materialize(task)
    assert {d.weekday() for d in _days(task)} == {0}

    task.recurrence_spec = {"kind": "weekly", "weekdays": [1]}
    task.save()
    materialize(task)

    future = [d for d in _days(task) if d > timezone.localdate()]
    assert {d.weekday() for d in future} == {1}, "old Mondays survived the rule change"


def test_changing_the_due_time_reschedules_the_horizon_rather_than_emptying_it(make_task):
    """Found by tracing it rather than by a failing test: filling the window
    before clearing the stale rows computed the scan's start from an instance
    that was about to be deleted, so a due-time change created nothing and then
    dropped all 90 future occasions — leaving the board, the calendar and every
    reminder empty until the next nightly run."""
    task = make_task(due_on=timezone.localdate(), due_time=time(9, 0),
                     recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})
    materialize(task)
    before = task.instances.count()

    task.due_time = time(7, 0)
    task.save()
    materialize(task)

    assert task.instances.count() >= before - 1, "the horizon was emptied"
    future_hours = {_local(i.due_at).hour
                    for i in task.instances.filter(due_at__gt=timezone.now())}
    assert future_hours == {7}, f"future occasions kept the old time: {future_hours}"


def test_history_is_never_backfilled(make_task):
    """A task created today whose rule anchors weeks ago must not conjure a
    fortnight of occasions nobody could have done — `close_passed` would
    immediately close every one as missed and invent a failure that never
    happened. Instances exist only from the moment the task did."""
    task = make_task(due_on=timezone.localdate() - timedelta(days=14),
                     recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})

    materialize(task)

    assert min(_days(task)) == timezone.localdate(), "history was fabricated"


def test_a_future_instance_someone_commented_on_is_never_silently_deleted(make_task, member):
    """Fixing a schedule must not take a person's note with it — that is a far
    worse bug than a leftover row."""
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})
    materialize(task)
    future = task.instances.filter(due_at__gt=timezone.now()).order_by("due_at").first()
    future.comments.create(author=member, body="bring the good shoes")

    task.recurrence_spec = {"kind": "yearly"}
    task.save()
    materialize(task)

    assert task.instances.filter(pk=future.pk).exists(), "a commented instance was deleted"


# ── materialisation: rolling ─────────────────────────────────────────────────

def test_a_rolling_task_holds_exactly_one_open_instance(make_task):
    """It cannot hold more: "3 days after I last did it" has no second date
    until the first is done."""
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.ROLLING,
                     recurrence_spec={"days": 3})

    materialize(task)
    materialize(task)

    assert task.instances.filter(outcome=InstanceOutcome.PENDING).count() == 1


def test_a_rolling_task_starts_on_its_due_date_not_an_interval_later(make_task):
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.ROLLING,
                     recurrence_spec={"days": 3})

    materialize(task)

    assert _days(task) == [timezone.localdate()]


def test_completing_a_rolling_task_schedules_the_next_one_interval_later(make_task):
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.ROLLING,
                     recurrence_spec={"days": 3})
    materialize(task)
    instance = current_instance(task)

    instance.outcome = InstanceOutcome.DONE
    instance.completed_at = timezone.now()
    instance.save()
    materialize(task)

    assert _days(task) == [timezone.localdate(), timezone.localdate() + timedelta(days=3)]


def test_a_rolling_task_counts_from_when_it_was_done_not_when_it_was_due(make_task):
    """The whole point of rolling: water the plants three days after you last
    watered them, not three days after you meant to."""
    task = make_task(due_on=timezone.localdate() - timedelta(days=10),
                     recurrence_type=RecurrenceType.ROLLING,
                     recurrence_spec={"days": 3})
    materialize(task)
    instance = current_instance(task)
    instance.outcome = InstanceOutcome.DONE
    instance.completed_at = timezone.now()  # done today, 10 days late
    instance.save()

    assert _local(next_rolling_due(task)).date() == timezone.localdate() + timedelta(days=3)


def test_a_rolling_task_with_an_unusable_interval_schedules_nothing(make_task):
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.ROLLING,
                     recurrence_spec={})

    assert materialize(task) == 0
    assert next_rolling_due(task) is None


# ── archived and deleted tasks go quiet ──────────────────────────────────────

def test_an_archived_task_is_not_scheduled(make_task):
    """"Not now" has to include the schedule, or a task someone deliberately
    put down keeps accruing misses against their history."""
    task = make_task(due_on=timezone.localdate(), state=TaskState.ARCHIVED,
                     recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})

    assert materialize(task) == 0
    assert task.instances.count() == 0


def test_a_soft_deleted_task_is_not_scheduled(make_task):
    task = make_task(due_on=timezone.localdate(), recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})
    task.delete()  # soft
    task.refresh_from_db()

    assert materialize(task) == 0


def test_the_nightly_job_skips_archived_tasks_but_does_the_rest(make_task):
    make_task(title="live", due_on=timezone.localdate())
    make_task(title="parked", due_on=timezone.localdate(), state=TaskState.ARCHIVED)

    result = materialize_open_tasks()

    assert result["created"] == 1
    assert result["failed"] == 0


def test_one_broken_rule_does_not_stop_the_rest_of_the_house_being_scheduled(make_task):
    """A spec typed by hand in the admin is exactly what fails here, and it
    should cost that task its schedule — not everyone's."""
    make_task(title="fine", due_on=timezone.localdate())
    make_task(title="broken", due_on=timezone.localdate(),
              recurrence_type=RecurrenceType.FIXED, recurrence_spec={"kind": "wat"})

    result = materialize_open_tasks()

    assert result["created"] == 1


# ── closing out what has gone past ───────────────────────────────────────────

def test_an_overdue_one_shot_stays_on_the_board_rather_than_becoming_history(make_task):
    """"Buy grout" from three months ago is still a real todo. Nothing later is
    coming to take its turn, so it stays open however overdue it looks."""
    task = make_task(due_on=timezone.localdate() - timedelta(days=90))
    materialize(task)

    close_passed_instances()

    assert current_instance(task) is not None
    assert task.instances.get().outcome == InstanceOutcome.PENDING


def test_a_rolling_task_never_auto_misses(make_task):
    """It cannot: by definition nothing later exists until this one is done."""
    task = make_task(due_on=timezone.localdate() - timedelta(days=30),
                     recurrence_type=RecurrenceType.ROLLING, recurrence_spec={"days": 3})
    materialize(task)

    close_passed_instances()

    assert task.instances.get().outcome == InstanceOutcome.PENDING


def test_a_week_of_skipped_days_closes_all_but_todays(daily_with_history):
    """§5's exact promise: the board does not grow seven cards. It shows the
    current one, and the rest sit in history where Reporting can see them."""
    task = daily_with_history(6)  # six past days plus today

    result = close_passed_instances()

    assert result["missed"] == 6
    assert task.instances.filter(outcome=InstanceOutcome.MISSED).count() == 6
    assert task.instances.filter(outcome=InstanceOutcome.PENDING).count() == 1


def test_closing_is_idempotent(daily_with_history):
    daily_with_history(3)
    close_passed_instances()

    assert close_passed_instances()["missed"] == 0


def test_a_future_instance_is_never_closed(make_task):
    task = make_task(due_on=timezone.localdate() + timedelta(days=1),
                     recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"})
    materialize(task)

    close_passed_instances()

    assert not task.instances.filter(outcome=InstanceOutcome.MISSED).exists()


def test_an_archived_tasks_instances_are_not_closed_as_missed(daily_with_history):
    """Parking something must not keep scoring misses against it."""
    task = daily_with_history(5)
    task.state = TaskState.ARCHIVED
    task.save()

    assert close_passed_instances()["missed"] == 0


def test_closing_announces_each_miss_to_the_platform(daily_with_history, signal_recorder):
    """Anything that wants to react to a miss should be able to without
    importing this app."""
    from nora_home.core.signals import item_missed

    daily_with_history(2)
    recorder = signal_recorder.watch(item_missed)

    close_passed_instances()

    assert len(recorder.calls) == 2


# ── retroactive editing ──────────────────────────────────────────────────────

def test_completing_an_old_instance_does_not_disturb_the_current_one(daily_with_history):
    """§4's promise, and the reason nothing in this app caches a count: mark
    last Monday done on Wednesday, and Wednesday's own occasion must not
    move, close, or duplicate."""
    task = daily_with_history(3)
    close_passed_instances()

    current = current_instance(task)
    old = task.instances.filter(outcome=InstanceOutcome.MISSED).order_by("due_at").first()

    old.outcome = InstanceOutcome.DONE
    old.completed_at = timezone.now()
    old.save()
    materialize(task)
    close_passed_instances()

    current.refresh_from_db()
    assert current_instance(task) == current, "the current occasion moved"
    assert current.outcome == InstanceOutcome.PENDING


def test_history_survives_a_retroactive_correction(daily_with_history):
    """The corrected day changes; the days either side of it do not."""
    task = daily_with_history(4)
    close_passed_instances()
    missed = list(task.instances.filter(outcome=InstanceOutcome.MISSED).order_by("due_at"))

    missed[1].outcome = InstanceOutcome.DONE
    missed[1].completed_at = timezone.now()
    missed[1].save()

    outcomes = [i.outcome for i in task.instances.order_by("due_at")[:3]]
    assert outcomes == [InstanceOutcome.MISSED, InstanceOutcome.DONE, InstanceOutcome.MISSED]


# ── the board's view of a task ───────────────────────────────────────────────

def test_the_current_instance_is_the_earliest_still_open(daily_with_history):
    task = daily_with_history(2)

    earliest = task.instances.order_by("due_at").first()
    assert current_instance(task) == earliest


def test_a_task_with_nothing_open_has_no_current_instance(make_task):
    task = make_task(due_on=MONDAY)
    materialize(task)
    task.instances.update(outcome=InstanceOutcome.DONE)

    assert current_instance(task) is None


# ── shared tasks ─────────────────────────────────────────────────────────────

def test_a_shared_task_can_be_closed_by_any_assignee(make_task, make_member):
    bob, carol = make_member("bob"), make_member("carol")
    task = make_task(due_on=MONDAY)
    task.assignees.set([bob, carol])
    materialize(task)

    done = api.complete(current_instance(task), member=carol)

    assert done.outcome == InstanceOutcome.DONE
    assert done.completed_by == carol


def test_the_owner_can_always_close_their_own_shared_task(make_task, make_member, member):
    task = make_task(due_on=MONDAY)
    task.assignees.set([make_member("bob")])
    materialize(task)

    assert api.complete(current_instance(task), member=member).completed_by == member


def test_someone_the_task_was_never_shared_with_cannot_close_it(make_task, make_member):
    task = make_task(due_on=MONDAY)
    task.assignees.set([make_member("bob")])
    materialize(task)

    with pytest.raises(PermissionDenied):
        api.complete(current_instance(task), member=make_member("stranger"))


def test_a_shared_task_is_on_every_assignees_board_and_the_owners(make_task, make_member, member):
    bob, carol = make_member("bob"), make_member("carol")
    task = make_task(due_on=MONDAY)
    task.assignees.set([bob, carol])

    for who in (member, bob, carol):
        assert list(api.tasks_for(who)) == [task]


def test_a_shared_task_appears_once_on_a_combined_board_not_once_per_assignee(
        make_task, make_member, member):
    """The M2M join duplicates rows without .distinct() — a bug that looks like
    a rendering fault and gets debugged in the template instead of the query."""
    bob, carol = make_member("bob"), make_member("carol")
    task = make_task(due_on=MONDAY)
    task.assignees.set([bob, carol])

    assert list(api.tasks_for([member, bob, carol])) == [task]


def test_scoping_to_nobody_returns_nothing_rather_than_everything(make_task):
    make_task(due_on=MONDAY)

    assert list(api.tasks_for([])) == []


def test_a_task_shared_with_nobody_still_belongs_to_its_owner(make_task, member, make_member):
    task = make_task(due_on=MONDAY)

    assert list(api.tasks_for(member)) == [task]
    assert list(api.tasks_for(make_member("stranger"))) == []


# ── effort splits, never multiplies ──────────────────────────────────────────

def test_effort_splits_across_the_people_sharing_a_task(make_task, make_member):
    """60 minutes shared three ways is 20 minutes each. Counted in full it
    would tell three people they have a full day of one hour's house work."""
    task = make_task(due_on=MONDAY, planned_minutes=60)
    task.assignees.set([make_member("bob"), make_member("carol"), make_member("dee")])
    materialize(task)

    assert api.effort_share_minutes(current_instance(task)) == 20


def test_the_split_adds_back_up_to_the_whole_job(make_task, make_member):
    task = make_task(due_on=MONDAY, planned_minutes=45)
    people = [make_member("bob"), make_member("carol")]
    task.assignees.set(people)
    materialize(task)
    instance = current_instance(task)

    assert sum(api.effort_share_minutes(instance, who) for who in people) == 45


def test_an_unshared_task_lands_wholly_on_its_owner(make_task, member):
    task = make_task(due_on=MONDAY, planned_minutes=45)
    materialize(task)

    assert api.effort_share_minutes(current_instance(task), member) == 45


def test_effort_is_zero_for_someone_who_is_not_doing_it(make_task, make_member):
    task = make_task(due_on=MONDAY, planned_minutes=60)
    task.assignees.set([make_member("bob")])
    materialize(task)

    assert api.effort_share_minutes(current_instance(task), make_member("stranger")) == 0.0


def test_an_unestimated_task_has_no_share_rather_than_a_share_of_zero(make_task, make_member):
    """None means "nobody said how long"; 0.0 means "not your work". A load
    calculation has to be able to tell those apart."""
    task = make_task(due_on=MONDAY)
    task.assignees.set([make_member("bob")])
    materialize(task)

    assert api.effort_share_minutes(current_instance(task)) is None


def test_the_split_uses_the_real_time_once_someone_records_it(make_task, make_member):
    bob, carol = make_member("bob"), make_member("carol")
    task = make_task(due_on=MONDAY, planned_minutes=60)
    task.assignees.set([bob, carol])
    materialize(task)

    api.complete(current_instance(task), member=bob, actual_minutes=30)

    assert api.effort_share_minutes(task.instances.get()) == 15


# ── approval ─────────────────────────────────────────────────────────────────

@pytest.fixture
def needs_approval(make_task, make_member):
    """A task whose completion the approver has to sign off, plus the two
    people involved: the one who does it and the one who says yes."""
    def _make(**kwargs):
        doer, approver = make_member("doer"), make_member("approver")
        task = make_task(due_on=MONDAY, approver=approver, **kwargs)
        task.assignees.set([doer])
        materialize(task)
        return task, doer, approver

    return _make


def test_completing_a_task_with_an_approver_stops_short_of_done(needs_approval):
    task, doer, _ = needs_approval()

    instance = api.complete(current_instance(task), member=doer)

    assert instance.outcome == InstanceOutcome.AWAITING_APPROVAL
    assert instance.completed_by == doer
    assert instance.approved_at is None


def test_awaiting_approval_leaves_the_boards_open_columns(needs_approval):
    """The work is finished, so the card goes — but it is not a completion
    until the approver says so."""
    task, doer, _ = needs_approval()
    api.complete(current_instance(task), member=doer)

    assert current_instance(task) is None


def test_approving_is_what_makes_it_done(needs_approval):
    task, doer, approver = needs_approval()
    api.complete(current_instance(task), member=doer)

    instance = api.approve(task.instances.get(), member=approver)

    assert instance.outcome == InstanceOutcome.DONE
    assert instance.approved_by == approver
    # The approver said yes; the doer still did it.
    assert instance.completed_by == doer


def test_only_the_approver_can_approve(needs_approval, make_member):
    task, doer, _ = needs_approval()
    api.complete(current_instance(task), member=doer)

    for who in (doer, make_member("stranger")):
        with pytest.raises(PermissionDenied):
            api.approve(task.instances.get(), member=who)


def test_a_task_with_no_approver_cannot_be_approved(make_task, member):
    task = make_task(due_on=MONDAY)
    materialize(task)
    api.complete(current_instance(task), member=member)

    with pytest.raises(ValidationError):
        api.approve(task.instances.get(), member=member)


def test_an_occasion_nobody_has_finished_cannot_be_approved(needs_approval):
    task, _, approver = needs_approval()

    with pytest.raises(ValidationError):
        api.approve(current_instance(task), member=approver)


def test_completing_twice_while_it_waits_on_the_approver_is_refused(needs_approval):
    task, doer, _ = needs_approval()
    api.complete(current_instance(task), member=doer)

    with pytest.raises(ValidationError):
        api.complete(task.instances.get(), member=doer)


# ── rejection ────────────────────────────────────────────────────────────────

def test_rejecting_puts_it_back_on_the_board(needs_approval):
    task, doer, approver = needs_approval()
    api.complete(current_instance(task), member=doer)

    instance = api.reject(task.instances.get(), member=approver, reason="Grout still wet")

    assert instance.outcome == InstanceOutcome.PENDING
    assert instance.completed_at is None and instance.completed_by is None
    assert current_instance(task) == instance


def test_the_reason_a_rejection_happened_is_retrievable(needs_approval):
    """"No" without a reason is what makes an approval workflow resented."""
    task, doer, approver = needs_approval()
    api.complete(current_instance(task), member=doer)
    api.reject(task.instances.get(), member=approver, reason="Grout still wet")

    (rejection,) = api.approval_history(task.instances.get()).filter(to_value="rejected")
    assert rejection.reason == "Grout still wet"
    assert rejection.actor == approver


@pytest.mark.parametrize("reason", ["", "   ", None])
def test_a_rejection_without_a_reason_is_refused(needs_approval, reason):
    task, doer, approver = needs_approval()
    api.complete(current_instance(task), member=doer)

    with pytest.raises(ValidationError):
        api.reject(task.instances.get(), member=approver, reason=reason)

    assert task.instances.get().outcome == InstanceOutcome.AWAITING_APPROVAL


def test_rejection_keeps_the_note_and_the_time_the_worker_recorded(needs_approval):
    """Deleting what someone typed because a third party said no is exactly
    the behaviour the approval design exists to avoid."""
    task, doer, approver = needs_approval()
    api.complete(current_instance(task), member=doer,
                 actual_minutes=25, note="Only managed the first coat")
    api.reject(task.instances.get(), member=approver, reason="Needs a second coat")

    instance = task.instances.get()
    assert instance.actual_minutes == 25
    assert instance.note == "Only managed the first coat"


def test_a_rejected_occasion_can_be_done_again_and_approved(needs_approval):
    task, doer, approver = needs_approval()
    api.complete(current_instance(task), member=doer)
    api.reject(task.instances.get(), member=approver, reason="Needs a second coat")

    api.complete(current_instance(task), member=doer)
    instance = api.approve(task.instances.get(), member=approver)

    assert instance.outcome == InstanceOutcome.DONE
    assert [c.to_value for c in api.approval_history(instance).order_by("created_at")] == [
        "submitted", "rejected", "submitted", "approved"]


def test_only_the_approver_can_reject(needs_approval, make_member):
    task, doer, _ = needs_approval()
    api.complete(current_instance(task), member=doer)

    with pytest.raises(PermissionDenied):
        api.reject(task.instances.get(), member=make_member("stranger"), reason="No")


# ── recurring tasks cannot have an approver ──────────────────────────────────

def test_a_recurring_task_refuses_an_approver(make_task, make_member):
    """Every occurrence of a daily task needing sign-off is an approval queue
    nobody keeps up with, and the first week of it teaches everyone to
    rubber-stamp."""
    task = make_task(recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"}, due_on=MONDAY)
    task.approver = make_member("approver")

    with pytest.raises(DjangoValidationError) as raised:
        task.full_clean()
    assert "approver" in raised.value.message_dict


def test_the_database_refuses_it_too(make_task, make_member, member):
    """A rule that lives only in application code is a rule a management
    command or a data import will quietly break."""
    with pytest.raises(IntegrityError):
        Task.objects.create(
            title="Rubber stamp", owner=member, priority=Priority.P2,
            recurrence_type=RecurrenceType.ROLLING, recurrence_spec={"days": 3},
            approver=make_member("approver"))


def test_a_one_shot_task_with_an_approver_validates_fine(make_task, make_member):
    task = make_task(due_on=MONDAY, approver=make_member("approver"))

    task.full_clean()  # no exception
    assert task.needs_approval


def test_awaiting_approval_does_not_close_a_rolling_recurrence(make_task, member):
    """Unreachable while approvals are non-recurring only — asserted so the
    rule stays true if that ever changes."""
    task = make_task(recurrence_type=RecurrenceType.ROLLING,
                     recurrence_spec={"days": 3}, due_on=MONDAY)
    materialize(task)
    task.instances.update(outcome=InstanceOutcome.AWAITING_APPROVAL,
                          completed_at=timezone.now())

    assert next_rolling_due(task) == due_at_on(task, MONDAY)


# ── what the rest of the house hears ─────────────────────────────────────────

def test_a_plain_completion_is_announced_to_the_platform(make_task, member, signal_recorder):
    signal_recorder.watch(item_completed)
    task = make_task(due_on=MONDAY)
    materialize(task)

    api.complete(current_instance(task), member=member)

    assert [c["member"] for c in signal_recorder.calls] == [member]


def test_nothing_is_announced_until_the_approver_says_yes(needs_approval, signal_recorder):
    """Firing on submission would let a receiver celebrate work that is about
    to be sent back."""
    signal_recorder.watch(item_completed)
    task, doer, approver = needs_approval()

    api.complete(current_instance(task), member=doer)
    assert signal_recorder.calls == []

    api.approve(task.instances.get(), member=approver)
    assert [c["member"] for c in signal_recorder.calls] == [doer]


# ── how sharing and approval meet the scheduler ──────────────────────────────

def test_a_deleted_task_is_on_nobodys_board(make_task, member):
    """`Task.objects` does not filter soft-deletes for you, so the scoping
    every board goes through has to — or every board shows them."""
    task = make_task(due_on=MONDAY)
    task.delete()

    assert list(api.tasks_for(member)) == []
    assert list(api.tasks_for(member, queryset=Task.objects.all())) == [task]


def test_an_archived_task_still_belongs_to_its_owner(make_task, member):
    """"Not now" is a column on the board, not a deletion."""
    task = make_task(due_on=MONDAY, state=TaskState.ARCHIVED)

    assert list(api.tasks_for(member)) == [task]


def test_an_occasion_waiting_on_its_approver_does_not_sprout_a_second_one(needs_approval):
    """The nightly job runs while it waits. `_materialize_one_shot` looks for a
    *pending* instance and finds none — it must not read that as "this task has
    never had one" and create a fresh card the doer has to finish twice."""
    task, doer, _ = needs_approval()
    api.complete(current_instance(task), member=doer)

    materialize(task)

    assert task.instances.count() == 1


def test_turning_an_approved_task_into_a_recurring_one_is_refused(make_task, make_member):
    """The realistic way this rule gets broken: not by creating a bad task, but
    by editing a good one until it is bad."""
    task = make_task(due_on=MONDAY, approver=make_member("approver"))

    task.recurrence_type = RecurrenceType.FIXED
    task.recurrence_spec = {"kind": "daily"}
    with pytest.raises(IntegrityError):
        task.save()


def test_amending_a_finished_occasion_does_not_announce_it_twice(make_task, member,
                                                                 signal_recorder):
    """Correcting last week's note must not make Slack congratulate someone
    again for work they finished days ago."""
    signal_recorder.watch(item_completed)
    task = make_task(due_on=MONDAY)
    materialize(task)
    api.complete(current_instance(task), member=member)

    finished_at = task.instances.get().completed_at

    api.complete(task.instances.get(), member=member, note="Took longer than I said")

    assert len(signal_recorder.calls) == 1
    instance = task.instances.get()
    assert instance.note == "Took longer than I said"
    # Restamping it would drift the history every chart is drawn from a little
    # further from the truth with each edit.
    assert instance.completed_at == finished_at


def test_amending_someone_elses_completion_does_not_steal_the_credit(
        make_task, member, make_member):
    bob = make_member("bob")
    task = make_task(due_on=MONDAY)
    task.assignees.set([bob, member])
    materialize(task)
    api.complete(current_instance(task), member=bob)

    api.complete(task.instances.get(), member=member, note="Adding a note for Bob")

    assert task.instances.get().completed_by == bob


def test_an_explicit_time_still_corrects_a_finished_occasion(make_task, member):
    """The escape hatch: `at=` is how a completion time is genuinely fixed."""
    task = make_task(due_on=MONDAY)
    materialize(task)
    api.complete(current_instance(task), member=member)
    truth = due_at_on(task, MONDAY)

    api.complete(task.instances.get(), member=member, at=truth)

    assert task.instances.get().completed_at == truth


def test_retroactively_marking_a_missed_day_done_is_announced(daily_with_history, member):
    """That one *is* a transition — §4's retroactive editing, working."""
    task = daily_with_history(2)
    close_passed_instances()
    missed = task.instances.filter(outcome=InstanceOutcome.MISSED).first()

    instance = api.complete(missed, member=member)

    assert instance.outcome == InstanceOutcome.DONE


# ── one-shot tasks leave the board when resolved ─────────────────────────────

def test_completing_a_one_shot_tasks_only_instance_finishes_the_task(make_task, member):
    """§4: "Done — finished, leaves the board, lives in history." """
    task = make_task(due_on=MONDAY)
    materialize(task)

    api.complete(current_instance(task), member=member)

    task.refresh_from_db()
    assert task.state == TaskState.DONE


def test_a_recurring_tasks_state_never_follows_its_instances(make_task, member):
    task = make_task(recurrence_type=RecurrenceType.FIXED,
                     recurrence_spec={"kind": "daily"}, due_on=MONDAY)
    materialize(task)

    api.complete(current_instance(task), member=member)

    task.refresh_from_db()
    assert task.state == TaskState.OPEN


def test_approving_a_one_shot_task_is_what_finishes_it_not_the_submission(
        needs_approval):
    task, doer, approver = needs_approval()

    api.complete(current_instance(task), member=doer)
    task.refresh_from_db()
    assert task.state == TaskState.OPEN

    api.approve(task.instances.get(), member=approver)
    task.refresh_from_db()
    assert task.state == TaskState.DONE


def test_skipping_a_one_shot_tasks_only_instance_also_finishes_the_task(make_task, member):
    task = make_task(due_on=timezone.localdate() + timedelta(days=3))
    materialize(task)

    api.skip(current_instance(task), member=member)

    task.refresh_from_db()
    assert task.state == TaskState.DONE


def test_a_skip_after_the_due_moment_is_refused(make_task, member):
    """After due_at it is a miss, not something still skippable (§5)."""
    task = make_task(due_on=MONDAY)
    materialize(task)
    instance = current_instance(task)

    with pytest.raises(ValidationError):
        api.skip(instance, member=member, at=instance.due_at + timedelta(minutes=1))


def test_undoing_a_completion_reopens_a_one_shot_task(make_task, member):
    task = make_task(due_on=MONDAY)
    materialize(task)
    api.complete(current_instance(task), member=member)

    instance = api.uncomplete(task.instances.get(), member=member)

    assert instance.outcome == InstanceOutcome.PENDING
    assert instance.completed_at is None
    task.refresh_from_db()
    assert task.state == TaskState.OPEN


def test_undoing_reopens_the_current_instance(make_task, member):
    task = make_task(due_on=MONDAY)
    materialize(task)
    api.complete(current_instance(task), member=member)

    api.uncomplete(task.instances.get(), member=member)

    assert current_instance(task) == task.instances.get()


def test_the_approver_can_undo_their_own_approval(needs_approval):
    task, doer, approver = needs_approval()
    api.complete(current_instance(task), member=doer)
    api.approve(task.instances.get(), member=approver)

    instance = api.uncomplete(task.instances.get(), member=approver)

    assert instance.outcome == InstanceOutcome.PENDING
    task.refresh_from_db()
    assert task.state == TaskState.OPEN


def test_a_stranger_cannot_undo_someone_elses_completion(make_task, member, make_member):
    task = make_task(due_on=MONDAY)
    materialize(task)
    api.complete(current_instance(task), member=member)

    with pytest.raises(PermissionDenied):
        api.uncomplete(task.instances.get(), member=make_member("stranger"))


def test_undoing_something_still_pending_is_refused(make_task, member):
    task = make_task(due_on=MONDAY)
    materialize(task)

    with pytest.raises(ValidationError):
        api.uncomplete(current_instance(task), member=member)
