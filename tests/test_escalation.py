"""
The escalation engine — "the part that makes Nora Home more than a todo list".

This is the subsystem where a bug is most expensive in both directions: a ladder
that does not climb means the house never tells anyone, and a ladder that climbs
twice means the house wakes everyone up repeatedly about one chore. Both are
tested here explicitly.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from nora_home.core.signals import escalation_raised, item_missed
from nora_home.notifications.models import Notification
from nora_home.tracker.escalation import close_expired_windows, escalate_due_occurrences
from nora_home.tracker.models import EscalationEvent, EscalationPolicy, Occurrence

pytestmark = pytest.mark.django_db


# ── the ladder climbs ────────────────────────────────────────────────────────

def test_nothing_escalates_before_it_is_due(make_trackable, make_occurrence, member):
    trackable = make_trackable(member)
    make_occurrence(trackable, minutes_overdue=-30)  # due in half an hour

    result = escalate_due_occurrences()

    assert result["raised"] == 0
    assert EscalationEvent.objects.count() == 0


def test_the_first_rung_fires_as_soon_as_it_is_overdue(make_trackable,
                                                       make_occurrence, member):
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 1
    assert occurrence.last_escalated_at is not None


def test_each_rung_fires_at_most_once(make_trackable, make_occurrence, member):
    """The sweep runs every five minutes. Without the escalation_level guard,
    every sweep would re-notify — the same chore nagging forever."""
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()
    escalate_due_occurrences()
    escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 1
    assert EscalationEvent.objects.filter(occurrence=occurrence).count() == 1


def test_the_ladder_advances_one_rung_per_sweep_as_time_passes(
        make_trackable, make_occurrence, member):
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=5)
    escalate_due_occurrences()

    # Now genuinely an hour late: the second rung's threshold.
    occurrence.due_at = timezone.now() - timedelta(minutes=65)
    occurrence.save(update_fields=["due_at"])
    escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 2


def test_the_ladder_stops_at_the_top(make_trackable, make_occurrence, household):
    trackable = make_trackable(household["kid"])
    occurrence = make_occurrence(trackable, minutes_overdue=10_000)

    for _ in range(6):
        escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 4, "there are only four rungs"


def test_grace_minutes_delay_the_first_rung(make_trackable, make_occurrence, member):
    policy = EscalationPolicy.objects.create(
        name="Gentle", grace_minutes=60,
        levels=[{"after_minutes": 0, "notify": "owner", "severity": "nudge"}])
    trackable = make_trackable(member, escalation_policy=policy)
    occurrence = make_occurrence(trackable, minutes_overdue=30)

    escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 0, "grace period was not honoured"


def test_a_policy_with_no_rungs_never_escalates(make_trackable, make_occurrence,
                                                member):
    policy = EscalationPolicy.objects.create(name="Silent", levels=[])
    trackable = make_trackable(member, escalation_policy=policy)
    make_occurrence(trackable, minutes_overdue=5000)

    assert escalate_due_occurrences()["raised"] == 0


# ── the ladder stops ─────────────────────────────────────────────────────────

def test_acknowledging_halts_the_ladder(make_trackable, make_occurrence, member,
                                        adult):
    """Acknowledging says "I know, leave me alone" without claiming it is done.
    If it did not stop the ladder, nobody would ever use it."""
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=5000)
    occurrence.acknowledge(adult)

    escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 0
    assert occurrence.acknowledged_by == adult


def test_completed_occurrences_do_not_escalate(make_trackable, make_occurrence,
                                               member):
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=5000)
    occurrence.complete(member)

    escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 0


@pytest.mark.parametrize("status", [
    Occurrence.Status.SKIPPED, Occurrence.Status.CANCELLED, Occurrence.Status.MISSED,
])
def test_only_pending_occurrences_escalate(make_trackable, make_occurrence, member,
                                           status):
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=5000, status=status)

    escalate_due_occurrences()

    occurrence.refresh_from_db()
    assert occurrence.escalation_level == 0


# ── audiences ────────────────────────────────────────────────────────────────

def test_the_owner_rung_notifies_only_the_owner(make_trackable, make_occurrence,
                                                household):
    trackable = make_trackable(household["kid"])
    make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()

    event = EscalationEvent.objects.get()
    assert list(event.notified.all()) == [household["kid"]]
    assert event.audience == "owner"


def test_the_chain_rung_notifies_the_first_contact(make_trackable, make_occurrence,
                                                   household):
    """Level 3 uses chain rung 1 — the ladder walks the chain one person at a
    time rather than telling everyone at once."""
    trackable = make_trackable(household["kid"])
    occurrence = make_occurrence(trackable, minutes_overdue=5)
    escalate_due_occurrences()
    occurrence.due_at = timezone.now() - timedelta(minutes=65)
    occurrence.save(update_fields=["due_at"])
    escalate_due_occurrences()

    occurrence.due_at = timezone.now() - timedelta(minutes=125)
    occurrence.save(update_fields=["due_at"])
    escalate_due_occurrences()

    level_three = EscalationEvent.objects.get(level=3)
    assert level_three.audience == "chain"
    assert list(level_three.notified.all()) == [household["adult"]]


def test_the_house_rung_notifies_everyone(make_trackable, make_occurrence,
                                          household):
    trackable = make_trackable(household["kid"])
    make_occurrence(trackable, minutes_overdue=10_000)
    for _ in range(4):
        escalate_due_occurrences()

    top = EscalationEvent.objects.get(level=4)

    assert top.audience == "house"
    assert set(top.notified.all()) == set(household.values())


def test_the_adults_rung_excludes_children(make_trackable, make_occurrence,
                                           household):
    policy = EscalationPolicy.objects.create(
        name="Adults only",
        levels=[{"after_minutes": 0, "notify": "adults", "severity": "alert"}])
    trackable = make_trackable(household["kid"], escalation_policy=policy)
    make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()

    notified = set(EscalationEvent.objects.get().notified.all())
    assert notified == {household["adult"], household["admin"]}
    assert household["kid"] not in notified


def test_an_unknown_audience_falls_back_to_the_owner(make_trackable,
                                                     make_occurrence, member):
    """A typo in an admin-edited policy must degrade to nudging the owner, not
    to notifying nobody or crashing the sweep."""
    policy = EscalationPolicy.objects.create(
        name="Typo", levels=[{"after_minutes": 0, "notify": "evrryone"}])
    trackable = make_trackable(member, escalation_policy=policy)
    make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()

    assert list(EscalationEvent.objects.get().notified.all()) == [member]


# ── notifications produced ───────────────────────────────────────────────────

def test_escalation_notifies_the_owner_with_a_useful_title(make_trackable,
                                                           make_occurrence, member):
    trackable = make_trackable(member, title="Take the bins out")
    make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()

    notification = Notification.objects.get()
    assert notification.recipient == member
    assert "Take the bins out" in notification.title


def test_a_chain_notification_names_the_person_who_is_late(make_trackable,
                                                           make_occurrence,
                                                           household):
    policy = EscalationPolicy.objects.create(
        name="Straight to chain",
        levels=[{"after_minutes": 0, "notify": "chain", "severity": "alert"}])
    trackable = make_trackable(household["kid"], title="Homework",
                               escalation_policy=policy)
    make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()

    body = Notification.objects.get(recipient=household["adult"])
    assert household["kid"].name in body.title


def test_repeat_sweeps_do_not_renotify(make_trackable, make_occurrence, member):
    trackable = make_trackable(member)
    make_occurrence(trackable, minutes_overdue=5)

    escalate_due_occurrences()
    escalate_due_occurrences()

    assert Notification.objects.count() == 1


# ── resilience ───────────────────────────────────────────────────────────────

def test_one_broken_occurrence_does_not_stop_the_others(make_trackable,
                                                        make_occurrence,
                                                        make_member, monkeypatch):
    """Failures degrade, never cascade (CLAUDE.md §6). One trackable with a bad
    policy must not stop the whole house from being reminded."""
    import nora_home.tracker.escalation as engine

    good_owner = make_member("good")
    bad_owner = make_member("bad")
    make_occurrence(make_trackable(bad_owner, title="Explodes"), minutes_overdue=10)
    make_occurrence(make_trackable(good_owner, title="Fine"), minutes_overdue=5)

    original = engine._advance

    def sometimes_explode(occurrence, now):
        if occurrence.trackable.title == "Explodes":
            raise RuntimeError("bad policy JSON")
        return original(occurrence, now)

    monkeypatch.setattr(engine, "_advance", sometimes_explode)

    result = escalate_due_occurrences()

    assert result["raised"] == 1, "the healthy occurrence was not escalated"


def test_the_sweep_is_bounded(make_trackable, make_occurrence, member):
    """Unbounded, one backlog would let a single sweep run for minutes and hold
    a worker the escalation queue needs."""
    trackable = make_trackable(member)
    for minutes in range(1, 8):
        make_occurrence(trackable, minutes_overdue=minutes * 10)

    assert escalate_due_occurrences(limit=3)["checked"] == 3


def test_escalation_raised_signal_fires(make_trackable, make_occurrence, member,
                                        signal_recorder):
    signal_recorder.watch(escalation_raised)
    make_occurrence(make_trackable(member), minutes_overdue=5)

    escalate_due_occurrences()

    assert len(signal_recorder.calls) == 1
    assert signal_recorder.calls[0]["level"] == 1


def test_escalation_writes_an_audit_row(make_trackable, make_occurrence, member):
    from nora_home.core.models import AuditEvent

    make_occurrence(make_trackable(member), minutes_overdue=5)

    escalate_due_occurrences()

    assert AuditEvent.objects.filter(action="escalation.raised").exists()


# ── expiry ───────────────────────────────────────────────────────────────────

def test_an_expired_window_becomes_missed(make_trackable, make_occurrence, member):
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=5000)
    occurrence.window_ends_at = timezone.now() - timedelta(hours=1)
    occurrence.save(update_fields=["window_ends_at"])

    assert close_expired_windows()["missed"] == 1
    occurrence.refresh_from_db()
    assert occurrence.status == Occurrence.Status.MISSED


def test_an_open_window_is_left_alone(make_trackable, make_occurrence, member):
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=30)

    close_expired_windows()

    occurrence.refresh_from_db()
    assert occurrence.status == Occurrence.Status.PENDING


def test_occurrences_with_no_window_never_expire(make_trackable, make_occurrence,
                                                 member):
    trackable = make_trackable(member)
    occurrence = make_occurrence(trackable, minutes_overdue=99_999,
                                 window_ends_at=None)

    close_expired_windows()

    occurrence.refresh_from_db()
    assert occurrence.status == Occurrence.Status.PENDING


def test_closing_a_window_fires_item_missed(make_trackable, make_occurrence,
                                            member, signal_recorder):
    signal_recorder.watch(item_missed)
    occurrence = make_occurrence(make_trackable(member), minutes_overdue=5000)
    occurrence.window_ends_at = timezone.now() - timedelta(hours=1)
    occurrence.save(update_fields=["window_ends_at"])

    close_expired_windows()

    assert len(signal_recorder.calls) == 1
    assert signal_recorder.calls[0]["member"] == member


def test_a_completed_occurrence_is_never_marked_missed(make_trackable,
                                                       make_occurrence, member):
    occurrence = make_occurrence(make_trackable(member), minutes_overdue=5000)
    occurrence.complete(member)
    occurrence.window_ends_at = timezone.now() - timedelta(hours=1)
    occurrence.save(update_fields=["window_ends_at"])

    close_expired_windows()

    occurrence.refresh_from_db()
    assert occurrence.status == Occurrence.Status.DONE


# ── the default policy ───────────────────────────────────────────────────────

def test_get_default_creates_a_house_policy_when_none_exists():
    policy = EscalationPolicy.get_default()

    assert policy.is_default is True
    assert len(policy.levels) == 4


def test_get_default_does_not_keep_creating_policies():
    EscalationPolicy.get_default()
    EscalationPolicy.get_default()

    assert EscalationPolicy.objects.filter(is_default=True).count() == 1


def test_a_trackable_with_no_policy_uses_the_house_default(make_trackable, member):
    trackable = make_trackable(member, escalation_policy=None)

    assert trackable.policy.is_default is True
