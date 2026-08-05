"""
The tracker's published API and its models.

`nora_home.tracker.api` is what house apps actually call — the promise made in
DEVELOPMENT.md that an app gets scheduling, streaks, and escalation for free by
registering a trackable instead of writing its own reminder logic. Its contract
is documented as safe to call from a model's `save()`, so idempotency is the
central thing tested here.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from nora_home.core.signals import item_completed
from nora_home.tracker.api import (
    complete_source,
    deactivate_trackable,
    open_items_for,
    register_trackable,
)
from nora_home.tracker.models import Cadence, Completion, EscalationPolicy, Occurrence, Trackable

pytestmark = pytest.mark.django_db


# ── registering ──────────────────────────────────────────────────────────────

def test_register_creates_a_trackable_and_its_occurrences(member):
    trackable = register_trackable(
        owner=member, title="Change the HVAC filter", app_slug="maintenance",
        source_ref="42", cadence=Cadence.MONTHLY)

    assert trackable.pk
    assert trackable.app_slug == "maintenance"
    assert trackable.occurrences.exists(), "no occurrences were materialized"


def test_registering_twice_updates_rather_than_duplicating(member):
    """Documented as safe to call from save(). If it duplicated, every edit to a
    habit would leave a second ghost copy nagging forever."""
    register_trackable(owner=member, title="Filter", app_slug="maintenance",
                       source_ref="42", cadence=Cadence.MONTHLY)
    register_trackable(owner=member, title="Filter (annual)", app_slug="maintenance",
                       source_ref="42", cadence=Cadence.YEARLY)

    assert Trackable.objects.filter(app_slug="maintenance", source_ref="42").count() == 1
    assert Trackable.objects.get().cadence == Cadence.YEARLY


def test_the_same_source_ref_in_different_apps_stays_separate(member):
    register_trackable(owner=member, title="A", app_slug="maintenance", source_ref="1")
    register_trackable(owner=member, title="B", app_slug="plants", source_ref="1")

    assert Trackable.objects.count() == 2


def test_registering_without_a_source_ref_always_creates(member):
    """No source_ref means the caller has nothing to key on — a one-off task, not
    a mirror of an app record."""
    register_trackable(owner=member, title="One off", app_slug="tracker")
    register_trackable(owner=member, title="One off", app_slug="tracker")

    assert Trackable.objects.count() == 2


def test_registering_reactivates_a_previously_deactivated_trackable(member):
    """Re-adding something you deleted should start working again, not stay
    silently dead because is_active was never cleared."""
    register_trackable(owner=member, title="Filter", app_slug="maintenance",
                       source_ref="42")
    deactivate_trackable(app_slug="maintenance", source_ref="42")

    register_trackable(owner=member, title="Filter", app_slug="maintenance",
                       source_ref="42")

    assert Trackable.objects.get().is_active is True


def test_an_overlong_title_is_truncated_not_rejected(member):
    trackable = register_trackable(owner=member, title="x" * 500, app_slug="tracker")

    assert len(trackable.title) == 160


def test_a_named_policy_is_resolved(member):
    EscalationPolicy.objects.create(name="Safety critical", levels=[])

    trackable = register_trackable(owner=member, title="Smoke alarm",
                                   app_slug="maintenance",
                                   escalation_policy="Safety critical")

    assert trackable.escalation_policy.name == "Safety critical"


def test_an_unknown_policy_name_falls_back_to_the_default(member):
    """A house app naming a policy that does not exist must still get escalation,
    not silently get none."""
    trackable = register_trackable(owner=member, title="x", app_slug="tracker",
                                   escalation_policy="Policy That Never Existed")

    assert trackable.escalation_policy is not None
    assert trackable.escalation_policy.is_default is True


# ── deactivating ─────────────────────────────────────────────────────────────

def test_deactivating_cancels_pending_occurrences(member):
    """Nothing must escalate about a record the app has already removed."""
    register_trackable(owner=member, title="Filter", app_slug="maintenance",
                       source_ref="42", cadence=Cadence.DAILY)

    deactivate_trackable(app_slug="maintenance", source_ref="42")

    assert not Occurrence.objects.filter(status=Occurrence.Status.PENDING).exists()
    assert Occurrence.objects.filter(status=Occurrence.Status.CANCELLED).exists()


def test_deactivating_keeps_the_history(member):
    trackable = register_trackable(owner=member, title="Filter",
                                   app_slug="maintenance", source_ref="42",
                                   cadence=Cadence.DAILY)
    occurrence = trackable.occurrences.order_by("due_at").first()
    occurrence.complete(member)

    deactivate_trackable(app_slug="maintenance", source_ref="42")

    occurrence.refresh_from_db()
    assert occurrence.status == Occurrence.Status.DONE
    assert Completion.objects.count() == 1


def test_deactivating_something_unknown_is_harmless(member):
    assert deactivate_trackable(app_slug="nope", source_ref="nope") == 0


# ── completing ───────────────────────────────────────────────────────────────

def test_complete_source_closes_the_soonest_open_occurrence(member):
    register_trackable(owner=member, title="Vitamins", app_slug="habits",
                       source_ref="7", cadence=Cadence.DAILY)
    earliest = Occurrence.objects.order_by("due_at").first()

    complete_source(app_slug="habits", source_ref="7", member=member)

    earliest.refresh_from_db()
    assert earliest.status == Occurrence.Status.DONE


def test_complete_source_records_the_evidence(member):
    register_trackable(owner=member, title="Weigh in", app_slug="health",
                       source_ref="1", cadence=Cadence.DAILY)

    completion = complete_source(app_slug="health", source_ref="1", member=member,
                                 note="after breakfast", value=74.2)

    assert completion.numeric_value == 74.2
    assert completion.note == "after breakfast"


def test_complete_source_returns_none_when_nothing_is_open(member):
    """A house app calling this twice must get a quiet None, not an exception
    that surfaces as a 500 on someone's phone."""
    register_trackable(owner=member, title="Vitamins", app_slug="habits",
                       source_ref="7", cadence=Cadence.ONCE)
    complete_source(app_slug="habits", source_ref="7", member=member)

    assert complete_source(app_slug="habits", source_ref="7", member=member) is None


def test_completing_a_recurring_item_keeps_the_schedule_topped_up(member):
    register_trackable(owner=member, title="Vitamins", app_slug="habits",
                       source_ref="7", cadence=Cadence.DAILY)
    before = Occurrence.objects.filter(status=Occurrence.Status.PENDING).count()

    complete_source(app_slug="habits", source_ref="7", member=member)

    after = Occurrence.objects.filter(status=Occurrence.Status.PENDING).count()
    assert after == before - 1, "materialize should have kept the horizon full"


def test_completing_fires_item_completed(member, signal_recorder,
                                         make_trackable, make_occurrence):
    signal_recorder.watch(item_completed)
    occurrence = make_occurrence(make_trackable(member))

    occurrence.complete(member)

    assert len(signal_recorder.calls) == 1
    assert signal_recorder.calls[0]["member"] == member


def test_completing_defaults_to_the_owner(make_trackable, make_occurrence, member):
    occurrence = make_occurrence(make_trackable(member))

    occurrence.complete()

    occurrence.refresh_from_db()
    assert occurrence.completed_by == member


def test_someone_else_can_complete_your_chore(make_trackable, make_occurrence,
                                              member, adult):
    """A parent doing the bins should be recorded as the parent, not the kid."""
    occurrence = make_occurrence(make_trackable(member))

    occurrence.complete(adult)

    occurrence.refresh_from_db()
    assert occurrence.completed_by == adult
    assert occurrence.trackable.owner == member


def test_skipping_is_recorded_distinctly_from_completing(make_trackable,
                                                         make_occurrence, member):
    occurrence = make_occurrence(make_trackable(member))

    occurrence.skip(member, reason="away")

    occurrence.refresh_from_db()
    assert occurrence.status == Occurrence.Status.SKIPPED
    assert Completion.objects.get().was_skip is True


# ── queries ──────────────────────────────────────────────────────────────────

def test_open_items_only_returns_this_persons_work(member, adult, make_trackable,
                                                   make_occurrence):
    make_occurrence(make_trackable(member, title="Mine"))
    make_occurrence(make_trackable(adult, title="Theirs"))

    items = list(open_items_for(member))

    assert len(items) == 1
    assert items[0].trackable.title == "Mine"


def test_open_items_are_soonest_first(member, make_trackable, make_occurrence):
    trackable = make_trackable(member)
    make_occurrence(trackable, minutes_overdue=10)
    make_occurrence(trackable, minutes_overdue=500)

    items = list(open_items_for(member))

    assert items[0].due_at < items[1].due_at


def test_open_items_excludes_completed_work(member, make_trackable, make_occurrence):
    occurrence = make_occurrence(make_trackable(member))
    occurrence.complete(member)

    assert list(open_items_for(member)) == []


def test_overdue_queryset_only_matches_pending_and_past(member, make_trackable,
                                                        make_occurrence):
    trackable = make_trackable(member)
    make_occurrence(trackable, minutes_overdue=60)
    make_occurrence(trackable, minutes_overdue=-60)
    done = make_occurrence(trackable, minutes_overdue=120)
    done.complete(member)

    assert Occurrence.objects.overdue().count() == 1


def test_for_members_covers_the_combined_house_view(member, adult, make_trackable,
                                                    make_occurrence):
    make_occurrence(make_trackable(member))
    make_occurrence(make_trackable(adult))

    assert Occurrence.objects.for_members([member, adult]).count() == 2


# ── streaks ──────────────────────────────────────────────────────────────────

def test_streak_counts_consecutive_completions(member, make_trackable):
    trackable = make_trackable(member)
    for days_ago in range(4, 0, -1):
        Occurrence.objects.create(
            trackable=trackable, due_at=timezone.now() - timedelta(days=days_ago),
            status=Occurrence.Status.DONE)

    assert trackable.current_streak() == 4


def test_a_miss_breaks_the_streak(member, make_trackable):
    trackable = make_trackable(member)
    Occurrence.objects.create(trackable=trackable,
                              due_at=timezone.now() - timedelta(days=3),
                              status=Occurrence.Status.DONE)
    Occurrence.objects.create(trackable=trackable,
                              due_at=timezone.now() - timedelta(days=2),
                              status=Occurrence.Status.MISSED)
    Occurrence.objects.create(trackable=trackable,
                              due_at=timezone.now() - timedelta(days=1),
                              status=Occurrence.Status.DONE)

    assert trackable.current_streak() == 1, "the streak counted past a miss"


def test_a_skip_does_not_break_the_streak(member, make_trackable):
    """Skipping is a deliberate, sanctioned "not today" — holidays should not
    punish someone the way forgetting does."""
    trackable = make_trackable(member)
    Occurrence.objects.create(trackable=trackable,
                              due_at=timezone.now() - timedelta(days=3),
                              status=Occurrence.Status.DONE)
    Occurrence.objects.create(trackable=trackable,
                              due_at=timezone.now() - timedelta(days=2),
                              status=Occurrence.Status.SKIPPED)
    Occurrence.objects.create(trackable=trackable,
                              due_at=timezone.now() - timedelta(days=1),
                              status=Occurrence.Status.DONE)

    assert trackable.current_streak() == 2


def test_no_history_is_a_zero_streak(member, make_trackable):
    assert make_trackable(member).current_streak() == 0


# ── occurrence helpers ───────────────────────────────────────────────────────

def test_is_overdue_and_minutes_overdue(make_trackable, make_occurrence, member):
    occurrence = make_occurrence(make_trackable(member), minutes_overdue=90)

    assert occurrence.is_overdue is True
    assert 89 <= occurrence.minutes_overdue <= 91


def test_a_future_occurrence_is_not_overdue(make_trackable, make_occurrence, member):
    occurrence = make_occurrence(make_trackable(member), minutes_overdue=-60)

    assert occurrence.is_overdue is False
    assert occurrence.minutes_overdue == 0


def test_is_recurring_distinguishes_one_offs(make_trackable, member):
    assert make_trackable(member, cadence=Cadence.DAILY).is_recurring is True
    assert make_trackable(member, cadence=Cadence.ONCE).is_recurring is False


# ── reading back what happened ───────────────────────────────────────────────
#
# These exist so a house app never has to import nora_home.tracker.models. The
# reference app did exactly that in five files until 2026-08-04, which meant
# every app copied from it inherited a rule violation and a failing suite.

def test_streak_for_reads_an_apps_record_without_its_models(member, make_trackable):
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    for days_ago in range(3, 0, -1):
        Occurrence.objects.create(
            trackable=trackable, due_at=timezone.now() - timedelta(days=days_ago),
            status=Occurrence.Status.DONE)

    from nora_home.tracker.api import streak_for

    assert streak_for(app_slug="habits", source_ref="7") == 3


def test_streak_for_an_unknown_record_is_zero_not_an_error(db):
    """A house app asking about a record the tracker has never seen should get a
    number, not an exception on someone's home screen."""
    from nora_home.tracker.api import streak_for

    assert streak_for(app_slug="habits", source_ref="nope") == 0


def test_is_done_today_sees_a_completion(member, make_trackable, make_occurrence):
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    make_occurrence(trackable).complete(member)

    from nora_home.tracker.api import is_done_today

    assert is_done_today(app_slug="habits", source_ref="7") is True


def test_is_done_today_is_false_before_it_is_done(member, make_trackable,
                                                  make_occurrence):
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    make_occurrence(trackable)

    from nora_home.tracker.api import is_done_today

    assert is_done_today(app_slug="habits", source_ref="7") is False


def test_is_done_today_ignores_yesterdays_completion(member, make_trackable):
    """The streak is the long view; "done today" is what greys out the button."""
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    occurrence = Occurrence.objects.create(
        trackable=trackable, due_at=timezone.now() - timedelta(days=1))
    occurrence.complete(member)
    Occurrence.objects.filter(pk=occurrence.pk).update(
        completed_at=timezone.now() - timedelta(days=1))

    from nora_home.tracker.api import is_done_today

    assert is_done_today(app_slug="habits", source_ref="7") is False


def test_history_is_newest_first_and_bounded(member, make_trackable):
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    for days_ago in range(5):
        Occurrence.objects.create(
            trackable=trackable, due_at=timezone.now() - timedelta(days=days_ago))

    from nora_home.tracker.api import history_for

    history = list(history_for(app_slug="habits", source_ref="7", limit=3))

    assert len(history) == 3
    assert history[0].due_at > history[1].due_at


def test_completion_stats_counts_done_and_missed(member, make_trackable):
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    # Distinct due_at values: (trackable, due_at) is unique.
    for offset, status in enumerate([Occurrence.Status.DONE, Occurrence.Status.DONE,
                                     Occurrence.Status.MISSED], start=1):
        Occurrence.objects.create(trackable=trackable, status=status,
                                  due_at=timezone.now() - timedelta(days=offset))

    from nora_home.tracker.api import completion_stats

    stats = completion_stats(app_slug="habits")

    assert stats["done"] == 2
    assert stats["missed"] == 1
    assert stats["total"] == 3
    assert stats["rate"] == 66.7


def test_completion_stats_rate_is_none_when_nothing_was_due(db):
    """None rather than 0: a gap in the chart is honest, a zero says "you
    failed" when there was nothing to do."""
    from nora_home.tracker.api import completion_stats

    assert completion_stats(app_slug="habits")["rate"] is None


def test_completion_stats_ignores_still_pending_work(member, make_trackable,
                                                     make_occurrence):
    """A week still in progress must not read as a week half-missed."""
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    make_occurrence(trackable, minutes_overdue=-60)

    from nora_home.tracker.api import completion_stats

    assert completion_stats(app_slug="habits")["total"] == 0


def test_completion_stats_can_be_scoped_to_members(member, adult, make_trackable):
    for owner in (member, adult):
        trackable = make_trackable(owner, app_slug="habits", source_ref=str(owner.pk))
        Occurrence.objects.create(trackable=trackable, status=Occurrence.Status.DONE,
                                  due_at=timezone.now() - timedelta(hours=1))

    from nora_home.tracker.api import completion_stats

    assert completion_stats(app_slug="habits", members=[member])["done"] == 1
    assert completion_stats(app_slug="habits")["done"] == 2


def test_completion_stats_respects_the_window(member, make_trackable):
    trackable = make_trackable(member, app_slug="habits", source_ref="7")
    Occurrence.objects.create(trackable=trackable, status=Occurrence.Status.DONE,
                              due_at=timezone.now() - timedelta(days=30))
    Occurrence.objects.create(trackable=trackable, status=Occurrence.Status.DONE,
                              due_at=timezone.now() - timedelta(hours=2))

    from nora_home.tracker.api import completion_stats

    recent = completion_stats(app_slug="habits",
                              since=timezone.now() - timedelta(days=7))

    assert recent["done"] == 1


def test_trackable_for_finds_an_apps_record(member, make_trackable):
    make_trackable(member, app_slug="habits", source_ref="7", title="Vitamins")

    from nora_home.tracker.api import trackable_for

    assert trackable_for(app_slug="habits", source_ref="7").title == "Vitamins"


def test_trackable_for_an_unknown_record_is_none(db):
    from nora_home.tracker.api import trackable_for

    assert trackable_for(app_slug="habits", source_ref="nope") is None
