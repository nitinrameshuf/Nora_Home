"""
Todo's escalation ladder, ported from the tracker's own — see the module
docstring in nora_home/todo/escalation.py for what changed and what didn't.
Written to mirror the deleted tests/test_escalation.py's coverage rather than
re-derive it, since this is meant to behave the same way that proven engine did.
Story 40 deleted the tracker, so this file is now the only test of the ladder.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from nora_home.accounts.models import HouseMember
from nora_home.core.signals import escalation_raised
from nora_home.notifications.models import Notification
from nora_home.todo.escalation import escalate_due_instances
from nora_home.todo.models import (
    ChangeEvent,
    EscalationPolicy,
    Priority,
    Task,
    TaskState,
)
from nora_home.todo.scheduling import current_instance, materialize

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_task(policy):
    """No `member` dependency, deliberately — several tests here also pull in
    `household`, which creates its own "kid"/"partner"/"nitin", and `member`
    would collide on username with `household`'s "kid" if both fixtures ran."""
    def _make(owner, *, minutes_overdue: int = 0, **kwargs):
        kwargs.setdefault("title", "Overdue thing")
        kwargs.setdefault("priority", Priority.P2)
        kwargs.setdefault("escalation_enabled", True)
        kwargs.setdefault("escalation_policy", policy)
        due_on = timezone.localdate() - timedelta(days=1)
        task = Task.objects.create(owner=owner, due_on=due_on, **kwargs)
        materialize(task)
        instance = current_instance(task)
        instance.due_at = timezone.now() - timedelta(minutes=minutes_overdue)
        instance.save(update_fields=["due_at"])
        return task

    return _make


def _instance(task):
    return current_instance(task)


# ── the ladder climbs ────────────────────────────────────────────────────────

def test_nothing_escalates_before_it_is_due(make_task, member):
    task = make_task(member, minutes_overdue=-30)

    result = escalate_due_instances()

    assert result["raised"] == 0
    assert _instance(task).escalation_level == 0


def test_an_escalation_disabled_task_never_escalates(make_task, member):
    task = make_task(member, minutes_overdue=500, escalation_enabled=False)

    escalate_due_instances()

    assert _instance(task).escalation_level == 0


def test_an_archived_task_never_escalates(make_task, member):
    task = make_task(member, minutes_overdue=500)
    task.state = TaskState.ARCHIVED
    task.save(update_fields=["state"])

    escalate_due_instances()

    assert _instance(task).escalation_level == 0


def test_the_first_rung_fires_as_soon_as_it_is_overdue(make_task, member):
    task = make_task(member, minutes_overdue=5)

    escalate_due_instances()

    instance = _instance(task)
    assert instance.escalation_level == 1
    assert instance.last_escalated_at is not None


def test_each_rung_fires_at_most_once(make_task, member):
    task = make_task(member, minutes_overdue=5)

    escalate_due_instances()
    escalate_due_instances()
    escalate_due_instances()

    assert _instance(task).escalation_level == 1
    assert Notification.objects.filter(app_slug="todo").count() == 1


def test_the_ladder_advances_as_time_passes(make_task, member):
    task = make_task(member, minutes_overdue=5)
    escalate_due_instances()
    assert _instance(task).escalation_level == 1

    instance = _instance(task)
    instance.due_at = timezone.now() - timedelta(minutes=65)
    instance.save(update_fields=["due_at"])

    escalate_due_instances()
    assert _instance(task).escalation_level == 2


def test_the_ladder_stops_at_the_top(make_task, household):
    """Each sweep advances at most one rung, however overdue the instance —
    six sweeps against a four-rung ladder must not go past the fourth."""
    task = make_task(household["kid"], minutes_overdue=10_000)

    for _ in range(6):
        escalate_due_instances()

    assert _instance(task).escalation_level == 4  # the test policy's four rungs
    Notification.objects.all().delete()
    escalate_due_instances()
    assert not Notification.objects.exists()


def test_a_policy_with_no_rungs_never_escalates(make_task, member):
    empty = EscalationPolicy.objects.create(name="Silent", levels=[])
    task = make_task(member, minutes_overdue=500, escalation_policy=empty)

    escalate_due_instances()

    assert _instance(task).escalation_level == 0


def test_a_task_with_no_explicit_policy_uses_the_house_default(member):
    default = EscalationPolicy.get_default()  # grace_minutes=15, so 5 late would not fire
    task = Task.objects.create(title="No policy set", owner=member, priority=Priority.P2,
                               due_on=timezone.localdate() - timedelta(days=1),
                               escalation_enabled=True)
    materialize(task)
    instance = current_instance(task)
    instance.due_at = timezone.now() - timedelta(minutes=20)
    instance.save(update_fields=["due_at"])

    escalate_due_instances()

    instance.refresh_from_db()
    assert instance.escalation_level == 1
    assert default.levels  # sanity: the default actually has rungs to climb


# ── stopping conditions ──────────────────────────────────────────────────────

def test_acknowledging_halts_the_ladder(make_task, member):
    from nora_home.todo import api

    task = make_task(member, minutes_overdue=500)
    api.acknowledge(_instance(task), member=member)

    result = escalate_due_instances()

    assert result["raised"] == 0
    assert _instance(task).escalation_level == 0


def test_completed_instances_do_not_escalate(make_task, member):
    from nora_home.todo import api

    task = make_task(member, minutes_overdue=5)
    api.complete(_instance(task), member=member)

    result = escalate_due_instances()

    assert result["raised"] == 0


def test_only_pending_instances_escalate(make_task, member):
    from nora_home.todo import api

    task = make_task(member, minutes_overdue=5)
    api.skip(_instance(task), member=member, at=timezone.now() - timedelta(days=2))

    result = escalate_due_instances()

    assert result["raised"] == 0


# ── audiences ────────────────────────────────────────────────────────────────

def test_the_owner_rung_notifies_only_the_owner(make_task, member):
    task = make_task(member, minutes_overdue=5)

    escalate_due_instances()

    notified = set(Notification.objects.filter(app_slug="todo").values_list("recipient", flat=True))
    assert notified == {member.pk}


def test_the_chain_rung_notifies_the_first_contact(make_task, household):
    """Level 3 uses chain rung 1 — the ladder walks the chain one person at a
    time rather than telling everyone at once. Each sweep only advances one
    rung, so getting to level 3 takes three sweeps, moving the due moment
    further back each time to cross each rung's threshold."""
    task = make_task(household["kid"], minutes_overdue=5)
    escalate_due_instances()

    instance = _instance(task)
    instance.due_at = timezone.now() - timedelta(minutes=65)
    instance.save(update_fields=["due_at"])
    escalate_due_instances()

    instance.due_at = timezone.now() - timedelta(minutes=125)
    instance.save(update_fields=["due_at"])
    escalate_due_instances()

    assert _instance(task).escalation_level == 3
    third_rung = Notification.objects.filter(
        app_slug="todo", body__icontains=household["kid"].name).exclude(
        title__startswith="Overdue:")
    assert third_rung.filter(recipient=household["adult"]).exists()


def test_the_house_rung_notifies_everyone(make_task, household):
    task = make_task(household["kid"], minutes_overdue=10_000)
    for _ in range(4):
        escalate_due_instances()

    assert _instance(task).escalation_level == 4
    assert Notification.objects.filter(app_slug="todo", recipient=None).exists()


def test_the_adults_rung_excludes_children(make_task, household):
    """A "notify: adults" rung must never wake a kid up about someone else's
    overdue chore."""
    adults_policy = EscalationPolicy.objects.create(
        name="Adults only", levels=[{"after_minutes": 0, "notify": "adults", "severity": "alert"}])
    kid2 = HouseMember.objects.create(username="kid2", role=HouseMember.Role.MEMBER,
                                      display_name="Kid Two")
    task = make_task(household["kid"], minutes_overdue=5, escalation_policy=adults_policy)

    escalate_due_instances()

    notified = set(Notification.objects.filter(app_slug="todo").values_list("recipient", flat=True))
    assert kid2.pk not in notified
    assert household["kid"].pk not in notified


def test_an_unknown_audience_falls_back_to_the_owner(make_task, member):
    bad_policy = EscalationPolicy.objects.create(
        name="Bad", levels=[{"after_minutes": 0, "notify": "nonsense", "severity": "warning"}])
    task = make_task(member, minutes_overdue=5, escalation_policy=bad_policy)

    escalate_due_instances()

    assert Notification.objects.filter(app_slug="todo", recipient=member).exists()


# ── audience is the owner alone, never the assignees ─────────────────────────

def test_a_shared_tasks_escalation_still_chases_only_the_owner(
        make_task, member, make_member):
    """Reminders fan out to every assignee; escalation does not. A shared task
    still has exactly one person the ladder chases, which is what keeps a
    chain-of-contacts ladder meaningful."""
    bob = make_member("bob")
    task = make_task(member, minutes_overdue=5)
    task.assignees.set([bob])

    escalate_due_instances()

    notified = set(Notification.objects.filter(app_slug="todo").values_list("recipient", flat=True))
    assert notified == {member.pk}


# ── history and signals ──────────────────────────────────────────────────────

def test_repeat_sweeps_do_not_renotify(make_task, member):
    task = make_task(member, minutes_overdue=5)

    escalate_due_instances()
    escalate_due_instances()

    assert Notification.objects.filter(app_slug="todo").count() == 1


def test_one_broken_task_does_not_stop_the_others(make_task, member, make_member, monkeypatch):
    good = make_task(member, minutes_overdue=5)
    bad = make_task(make_member("other"), minutes_overdue=5, title="Broken")

    import nora_home.todo.escalation as escalation_module
    real_advance = escalation_module._advance

    def flaky(instance, now):
        if instance.task_id == bad.pk:
            raise RuntimeError("boom")
        return real_advance(instance, now)

    monkeypatch.setattr(escalation_module, "_advance", flaky)

    result = escalate_due_instances()

    assert result["raised"] == 1
    assert _instance(good).escalation_level == 1


def test_escalation_raised_signal_fires(make_task, member, signal_recorder):
    signal_recorder.watch(escalation_raised)
    task = make_task(member, minutes_overdue=5)

    escalate_due_instances()

    assert len(signal_recorder.calls) == 1
    assert signal_recorder.calls[0]["level"] == 1


def test_escalation_writes_a_changeevent(make_task, member):
    task = make_task(member, minutes_overdue=5)

    escalate_due_instances()

    events = ChangeEvent.objects.filter(task=task, field="escalation")
    assert events.count() == 1
    assert events.first().to_value == 1


def test_acknowledging_records_who_and_when(make_task, member):
    from nora_home.todo import api

    task = make_task(member, minutes_overdue=5)
    instance = api.acknowledge(_instance(task), member=member)

    assert instance.acknowledged_by == member
    assert instance.acknowledged_at is not None


# ── the policy's move from the tracker (Story 40) ────────────────────────────

def test_the_escalation_policy_belongs_to_todo_now():
    """The FK used to be a string reference to tracker.EscalationPolicy, which
    was the one thing keeping a Level 2 app pointed at a Level 1 one it was
    replacing. Story 40 deleted the tracker; this is what says the move landed."""
    field = Task._meta.get_field("escalation_policy")

    assert field.related_model is EscalationPolicy
    assert field.related_model._meta.app_label == "todo"


def test_a_house_with_no_policy_configured_still_escalates(member):
    """get_default() creates one rather than raising. An escalation that fired
    inside a Celery beat job and blew up on a missing row would fail silently,
    which is the opposite of what escalation is for."""
    EscalationPolicy.objects.all().delete()

    policy = EscalationPolicy.get_default()

    assert policy.pk
    assert policy.is_default
    assert len(policy.levels) == 4


def test_get_default_reuses_the_seeded_policy_rather_than_making_another():
    seeded = EscalationPolicy.objects.create(
        name="House default", is_default=True,
        levels=[{"after_minutes": 0, "notify": "owner", "severity": "nudge"}])

    assert EscalationPolicy.get_default() == seeded
    assert EscalationPolicy.objects.filter(is_default=True).count() == 1


def test_bootstrap_seeds_the_three_policies_onto_todo():
    from django.core.management import call_command

    EscalationPolicy.objects.all().delete()
    call_command("bootstrap_home")

    assert set(EscalationPolicy.objects.values_list("name", flat=True)) == {
        "House default", "Gentle", "Safety critical"}
