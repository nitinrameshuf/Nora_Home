"""
What a house app calls to get tracking for free.

    from nora_home.tracker.api import register_trackable, complete_source

    register_trackable(
        owner=request.user,
        title="Change the HVAC filter",
        app_slug="maintenance",
        source_ref=str(filter_record.pk),
        cadence="quarterly",
        url=f"/app/maintenance/{filter_record.pk}/",
        kind="maintenance",
    )

Calling it again with the same (app_slug, source_ref) updates rather than
duplicates, so it is safe to call from a model's save().
"""

from __future__ import annotations

import logging

from nora_home.tracker.models import EscalationPolicy, Occurrence, Trackable
from nora_home.tracker.scheduling import materialize

logger = logging.getLogger(__name__)


def register_trackable(*, owner, title: str, app_slug: str, source_ref: str = "",
                       cadence: str = "once", url: str = "", kind: str = "task",
                       notes: str = "", due_time=None, starts_on=None, ends_on=None,
                       interval_days: int | None = None, cron_expression: str = "",
                       escalation_policy: str | EscalationPolicy | None = None,
                       requires_evidence: bool = False, priority: int = 2,
                       tags: list[str] | None = None,
                       show_on_wall: bool = True) -> Trackable:
    """Create or update the trackable for an app record, and materialize its
    upcoming occurrences."""
    policy = _resolve_policy(escalation_policy)

    defaults = {
        "title": title[:160], "owner": owner, "kind": kind, "notes": notes,
        "cadence": cadence, "url": url, "due_time": due_time,
        "interval_days": interval_days, "cron_expression": cron_expression,
        "escalation_policy": policy, "requires_evidence": requires_evidence,
        "priority": priority, "tags": tags or [], "show_on_wall": show_on_wall,
        "is_active": True, "deleted_at": None,
    }
    if starts_on:
        defaults["starts_on"] = starts_on
    if ends_on:
        defaults["ends_on"] = ends_on

    if source_ref:
        trackable, created = Trackable.objects.update_or_create(
            app_slug=app_slug, source_ref=source_ref, defaults=defaults)
    else:
        trackable = Trackable.objects.create(app_slug=app_slug, **defaults)
        created = True

    materialize(trackable)
    logger.info("%s trackable %s for %s",
                "Created" if created else "Updated", trackable.title, app_slug)
    return trackable


def deactivate_trackable(*, app_slug: str, source_ref: str) -> int:
    """Stop tracking without destroying the history. Pending occurrences are
    cancelled so nothing escalates about a record the app already removed."""
    trackables = Trackable.objects.filter(app_slug=app_slug, source_ref=source_ref)
    Occurrence.objects.filter(trackable__in=trackables,
                              status=Occurrence.Status.PENDING).update(
        status=Occurrence.Status.CANCELLED)
    return trackables.update(is_active=False)


def complete_source(*, app_slug: str, source_ref: str, member=None, note: str = "",
                    value=None):
    """Mark the current open occurrence for an app record as done.

    Call this from your own 'mark done' flow so streaks and escalation stay in
    sync with your app's own state.
    """
    occurrence = (Occurrence.objects
                  .open()
                  .filter(trackable__app_slug=app_slug, trackable__source_ref=source_ref)
                  .select_related("trackable")
                  .order_by("due_at")
                  .first())
    if occurrence is None:
        logger.debug("No open occurrence for %s/%s", app_slug, source_ref)
        return None
    completion = occurrence.complete(member=member, note=note, value=value)
    materialize(occurrence.trackable)
    return completion


def open_items_for(member, limit: int = 50):
    """Everything this person still owes the house, soonest first."""
    return (Occurrence.objects
            .open()
            .for_member(member)
            .select_related("trackable")
            .order_by("due_at")[:limit])


# ── reading back what happened ───────────────────────────────────────────────
#
# These exist so a house app never has to import nora_home.tracker.models. That
# rule (CLAUDE.md §6) is what lets an app be uninstalled without breaking the
# house — but until 2026-08-04 the API had no way to answer "what is the streak
# on this record", so the reference app reached into the models directly and
# every app copied from it inherited the violation.


def streak_for(*, app_slug: str, source_ref: str) -> int:
    """Consecutive completions on an app's record, newest first, until a miss.

        streak_for(app_slug="habits", source_ref=str(habit.pk))
    """
    trackable = trackable_for(app_slug=app_slug, source_ref=source_ref)
    return trackable.current_streak() if trackable else 0


def trackable_for(*, app_slug: str, source_ref: str):
    """The Trackable behind one of your records, or None.

    Prefer the other helpers here; reach for this only when you need something
    they do not expose, and treat what comes back as read-only.
    """
    return Trackable.objects.filter(app_slug=app_slug, source_ref=source_ref).first()


def is_done_today(*, app_slug: str, source_ref: str) -> bool:
    """Was this record completed today, in house-local time?"""
    from django.utils import timezone

    return Occurrence.objects.filter(
        trackable__app_slug=app_slug,
        trackable__source_ref=source_ref,
        status=Occurrence.Status.DONE,
        completed_at__date=timezone.localdate(),
    ).exists()


def history_for(*, app_slug: str, source_ref: str, limit: int = 60):
    """This record's occurrences, newest first — for a detail page or a chart."""
    return (Occurrence.objects
            .filter(trackable__app_slug=app_slug, trackable__source_ref=source_ref)
            .order_by("-due_at")[:limit])


def completion_stats(*, app_slug: str, members=None, since=None, until=None) -> dict:
    """How much of what was due actually got done.

    Returns {"done", "missed", "total", "rate"} — `rate` is a percentage, or None
    when nothing was due in the window. None rather than 0 on purpose: a gap is
    honest, a zero says "you failed" when there was nothing to do.

        completion_stats(app_slug="habits", members=[request.user],
                         since=last_monday, until=this_monday)
    """
    occurrences = Occurrence.objects.filter(trackable__app_slug=app_slug)
    if members is not None:
        occurrences = occurrences.filter(trackable__owner__in=members)
    if since is not None:
        occurrences = occurrences.filter(due_at__gte=since)
    if until is not None:
        occurrences = occurrences.filter(due_at__lt=until)

    done = occurrences.filter(status=Occurrence.Status.DONE).count()
    missed = occurrences.filter(status=Occurrence.Status.MISSED).count()
    total = done + missed
    return {
        "done": done,
        "missed": missed,
        "total": total,
        "rate": round(done / total * 100, 1) if total else None,
    }


def _resolve_policy(value) -> EscalationPolicy | None:
    if value is None:
        return EscalationPolicy.get_default()
    if isinstance(value, EscalationPolicy):
        return value
    policy = EscalationPolicy.objects.filter(name=value).first()
    if policy is None:
        logger.warning("Unknown escalation policy %r; using the house default", value)
        return EscalationPolicy.get_default()
    return policy
