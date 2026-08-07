"""
The telemetry/integration bridge (docs/Main_App/subsystems/todo.md §8) and the
system board (`/todo/system/`).

`nora_home.todo.system_tasks` is tested two ways: directly against
`create_system_task()` for the dedupe rule that is the whole point of the
module, and through the real signals for the two things it is actually wired
to listen for — a threshold crossing and a repeatedly-failing integration —
since a receiver that is never connected is invisible to a direct call.
"""

from __future__ import annotations

import pytest
from django.urls import reverse

from nora_home.accounts.models import HouseMember
from nora_home.core.signals import integration_failing, threshold_crossed
from nora_home.integrations.models import Integration
from nora_home.telemetry.models import Series
from nora_home.todo.models import Priority, Task, TaskSource, TaskState
from nora_home.todo.system_tasks import create_system_task

pytestmark = pytest.mark.django_db


@pytest.fixture
def series():
    return Series.objects.create(key="pi.temp", label="Pi temperature", unit="°C",
                                 alert_above=80, precision=1)


@pytest.fixture
def integration():
    return Integration.objects.create(slug="weather", name="Weather")


# ── create_system_task: the dedupe rule ─────────────────────────────────────

def test_a_system_task_needs_an_active_adult_to_own_it(member):
    """`member` (tests/conftest.py) is role=MEMBER — a kid, not an adult. A
    freshly provisioned house with no adult added yet must not 500 on its
    first threshold breach."""
    task = create_system_task(origin_ref="x", title="Something happened")

    assert task is None
    assert Task.objects.count() == 0


def test_a_system_task_is_owned_by_the_admin_when_there_is_one(household):
    task = create_system_task(origin_ref="x", title="Something happened")

    assert task.owner == household["admin"]
    assert task.source == TaskSource.SYSTEM


def test_a_system_task_falls_back_to_an_adult_with_no_admin(adult):
    task = create_system_task(origin_ref="x", title="Something happened")

    assert task.owner == adult


def test_every_active_adult_is_an_assignee_so_anyone_can_pick_it_up(household):
    task = create_system_task(origin_ref="x", title="Something happened")

    assignees = set(task.assignees.all())
    assert assignees == {household["admin"], household["adult"]}
    assert household["kid"] not in assignees


def test_a_second_call_with_the_same_origin_reuses_the_open_task(household):
    """The dedupe rule this module exists for: a threshold that stays
    breached, or an integration that keeps failing, must not fill the board
    with duplicates of the same problem."""
    first = create_system_task(origin_ref="telemetry:x:alert", title="First wording")
    second = create_system_task(origin_ref="telemetry:x:alert", title="Second wording")

    assert first.pk == second.pk
    assert Task.objects.filter(source=TaskSource.SYSTEM).count() == 1
    # The reused task keeps its original wording — a later call updates
    # nothing about it, it only avoids creating a second one.
    assert Task.objects.get(pk=first.pk).title == "First wording"


def test_once_resolved_the_next_occurrence_is_a_fresh_task(household):
    """A completed system task is the problem being fixed, not muted — the
    next breach of the same thing is a new occurrence of it, not a
    continuation of the old one."""
    first = create_system_task(origin_ref="telemetry:x:alert", title="First")
    first.state = TaskState.DONE
    first.save()

    second = create_system_task(origin_ref="telemetry:x:alert", title="Second")

    assert second.pk != first.pk
    assert Task.objects.filter(source=TaskSource.SYSTEM).count() == 2


def test_different_origins_never_collapse_into_one_task(household):
    a = create_system_task(origin_ref="telemetry:a:alert", title="A")
    b = create_system_task(origin_ref="telemetry:b:alert", title="B")

    assert a.pk != b.pk


def test_a_system_task_gets_an_instance_so_it_can_be_ticked_off(household):
    """Board cards act through task.current, a materialised Instance — a
    system task with none would render with no tick button at all."""
    task = create_system_task(origin_ref="x", title="Something happened")

    assert task.instances.count() == 1


def test_a_system_task_gets_a_reminder(household):
    task = create_system_task(origin_ref="x", title="Something happened")

    assert task.reminders.exists()


# ── the telemetry bridge ─────────────────────────────────────────────────────

def test_a_threshold_crossing_creates_a_system_task(household, series):
    threshold_crossed.send(sender=Series, series=series, value=91.0,
                           threshold="alert", direction="above")

    task = Task.objects.get(source=TaskSource.SYSTEM)
    assert "Pi temperature" in task.title
    assert task.priority == Priority.P1
    assert task.origin_ref == "telemetry:pi.temp:alert"


def test_a_warning_threshold_is_lower_priority_than_an_alert(household, series):
    threshold_crossed.send(sender=Series, series=series, value=81.0,
                           threshold="warning", direction="above")

    assert Task.objects.get(source=TaskSource.SYSTEM).priority == Priority.P2


def test_a_stuck_sensor_does_not_fill_the_board(household, series):
    """`_raise_threshold` (telemetry/api.py) fires threshold_crossed on every
    off-threshold reading — this is what keeps that from becoming one task per
    reading while the sensor stays stuck."""
    for _ in range(5):
        threshold_crossed.send(sender=Series, series=series, value=91.0,
                               threshold="alert", direction="above")

    assert Task.objects.filter(source=TaskSource.SYSTEM).count() == 1


def test_telemetry_is_never_written_back_to(household, series):
    """§8.2: "One-directional." Completing the system task must not touch the
    series or its thresholds — telemetry stays telemetry."""
    task = create_system_task(origin_ref="telemetry:pi.temp:alert", title="Hot")
    task.state = TaskState.DONE
    task.save()

    series.refresh_from_db()
    assert series.alert_above == 80


# ── the integration bridge ───────────────────────────────────────────────────

def test_a_failing_integration_creates_a_system_task(household, integration):
    integration_failing.send(sender=Integration, integration=integration,
                             consecutive_failures=3, message="503 Service Unavailable")

    task = Task.objects.get(source=TaskSource.SYSTEM)
    assert "Weather" in task.title
    assert "503" in task.description
    assert task.origin_ref == f"integration:{integration.pk}"


def test_a_recovered_then_re_failing_integration_gets_a_fresh_task(household, integration):
    """integration_failing fires once per continuous-failure episode
    (nora_home.integrations.tasks) — a recovery in between means this is a
    second, unrelated episode, not a continuation of the first."""
    integration_failing.send(sender=Integration, integration=integration,
                             consecutive_failures=3, message="first outage")
    Task.objects.filter(source=TaskSource.SYSTEM).update(state=TaskState.DONE)

    integration_failing.send(sender=Integration, integration=integration,
                             consecutive_failures=3, message="second outage")

    assert Task.objects.filter(source=TaskSource.SYSTEM).count() == 2


# ── the real integrations.tasks wiring ───────────────────────────────────────

def test_the_third_consecutive_failure_fires_the_signal(household, integration):
    """Not a call to create_system_task directly — through the actual
    integrations.tasks._record_failure path, so a rename of the signal or a
    dropped .send() call would fail here even though system_tasks.py itself
    never changed."""
    from nora_home.integrations.tasks import _record_failure

    for _ in range(3):
        _record_failure(integration, "boom", 0.0, expected=True)

    assert Task.objects.filter(source=TaskSource.SYSTEM,
                               origin_ref=f"integration:{integration.pk}").exists()


# ── the system board ─────────────────────────────────────────────────────────

def test_the_system_board_shows_system_tasks_only(client, household):
    Task.objects.create(title="User task", owner=household["admin"], priority=Priority.P2,
                        source=TaskSource.USER)
    create_system_task(origin_ref="x", title="System task")
    client.force_login(household["admin"])

    response = client.get(reverse("todo:system_board"))
    body = response.content.decode()

    assert "System task" in body
    assert "User task" not in body


def test_the_user_board_never_shows_system_tasks(client, household):
    create_system_task(origin_ref="x", title="System task")
    client.force_login(household["admin"])

    body = client.get(reverse("todo:board")).content.decode()

    assert "System task" not in body


def test_a_kid_does_not_see_system_tasks_they_are_not_assigned_to(client, household):
    """Assignees are every active adult (above) — a member who is not one of
    them sees the same empty board scope_members already gives them
    everywhere else, not a special case for this page."""
    create_system_task(origin_ref="x", title="System task")
    client.force_login(household["kid"])

    body = client.get(reverse("todo:system_board")).content.decode()

    # The card, not the raw page: since 2026-08-07 the sidebar carries the
    # app's own section names, so searching the whole body matches navigation
    # as readily as content — this asserted "System task" and started failing
    # the moment a section was called "System tasks".
    assert 'class="todo-card__title"' not in body


def test_the_system_board_has_no_create_button(client, household):
    create_system_task(origin_ref="x", title="System task")
    client.force_login(household["admin"])

    body = client.get(reverse("todo:system_board")).content.decode()

    assert "New task" not in body


def test_a_label_link_on_the_system_board_stays_on_the_system_board(client, household):
    """board.html is one template for both boards — this is the regression
    test for the bug that shape invites: a filter link built with the wrong
    URL name would silently bounce someone from /todo/system/ back to /todo/."""
    from nora_home.todo.models import Label

    task = create_system_task(origin_ref="x", title="System task")
    task.labels.add(Label.objects.create(name="house"))
    client.force_login(household["admin"])

    body = client.get(reverse("todo:system_board")).content.decode()

    assert '/todo/system/?label=house' in body
    assert 'href="/todo/?label=house"' not in body


def test_completing_a_system_task_works_like_any_other(client, household):
    task = create_system_task(origin_ref="x", title="System task")
    instance = task.instances.get()
    client.force_login(household["admin"])

    response = client.post(reverse("todo:complete", args=[instance.uuid]))

    assert response.status_code in (302, 200)
    instance.refresh_from_db()
    assert instance.outcome == "done"
