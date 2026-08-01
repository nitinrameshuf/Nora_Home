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
