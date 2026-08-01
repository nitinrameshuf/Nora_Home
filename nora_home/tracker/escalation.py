"""
The escalation engine — the part that makes Nora Home more than a todo list.

For each overdue occurrence the engine walks its policy's ladder. Each rung has a
delay past the due time, an audience, and a severity. Once acknowledged or
completed, the ladder stops.

Audiences:
    owner   the person responsible
    chain   the next rung of that person's escalation_contacts (level 1, then 2…)
    adults  every adult in the house
    house   everyone, plus the escalation Slack channel and the wall display
"""

from __future__ import annotations

import logging

from django.utils import timezone

from nora_home.core.audit import record
from nora_home.core.signals import escalation_raised, item_missed
from nora_home.notifications.api import notify, notify_house
from nora_home.tracker.models import EscalationEvent, Occurrence

logger = logging.getLogger(__name__)


def escalate_due_occurrences(limit: int = 200) -> dict:
    """Advance the ladder for everything currently overdue. Safe to run every
    5 minutes; each rung fires at most once thanks to escalation_level."""
    now = timezone.now()
    candidates = (Occurrence.objects
                  .overdue(now)
                  .filter(acknowledged_at__isnull=True)
                  .select_related("trackable", "trackable__owner",
                                  "trackable__escalation_policy")
                  .order_by("due_at")[:limit])

    raised = 0
    for occurrence in candidates:
        try:
            if _advance(occurrence, now):
                raised += 1
        except Exception:
            logger.exception("Escalation failed for occurrence %s", occurrence.pk)

    return {"checked": len(candidates), "raised": raised}


def _advance(occurrence: Occurrence, now) -> bool:
    policy = occurrence.trackable.policy
    levels = policy.levels or []
    if occurrence.escalation_level >= len(levels):
        return False

    overdue_minutes = (now - occurrence.due_at).total_seconds() / 60 - policy.grace_minutes
    rung = levels[occurrence.escalation_level]
    if overdue_minutes < float(rung.get("after_minutes", 0)):
        return False

    audience = rung.get("notify", "owner")
    severity = rung.get("severity", "warning")
    channels = rung.get("channels")
    level = occurrence.escalation_level + 1

    recipients = _resolve_audience(occurrence, audience, level)
    _send(occurrence, recipients, audience, severity, channels, level)

    event = EscalationEvent.objects.create(
        occurrence=occurrence, level=level, severity=severity, audience=audience,
        detail={"minutes_overdue": int(overdue_minutes + policy.grace_minutes)},
    )
    if recipients:
        event.notified.set(recipients)

    occurrence.escalation_level = level
    occurrence.last_escalated_at = now
    occurrence.save(update_fields=["escalation_level", "last_escalated_at", "updated_at"])

    escalation_raised.send(sender=Occurrence, item=occurrence, level=level,
                           notified=recipients)
    record("tracker", "escalation.raised",
           subject=occurrence.trackable.title, severity="alert" if level >= 3 else "warning",
           source="celery", level=level, audience=audience,
           occurrence=str(occurrence.uuid))
    logger.info("Escalated '%s' to level %s (%s)",
                occurrence.trackable.title, level, audience)
    return True


def _resolve_audience(occurrence: Occurrence, audience: str, level: int) -> list:
    from nora_home.accounts.models import HouseMember

    owner = occurrence.trackable.owner
    if audience == "owner":
        return [owner]
    if audience == "chain":
        chain = owner.escalation_chain()
        # Level 3 uses chain rung 1, level 4 uses rung 2, and so on.
        index = max(0, level - 3)
        return chain[index:index + 1] or chain[:1]
    if audience == "adults":
        return list(HouseMember.objects.filter(
            is_active=True, role__in=[HouseMember.Role.ADULT, HouseMember.Role.ADMIN]))
    if audience == "house":
        return list(HouseMember.objects.filter(is_active=True))
    logger.warning("Unknown escalation audience %r; defaulting to owner", audience)
    return [owner]


def _send(occurrence: Occurrence, recipients, audience: str, severity: str,
          channels, level: int):
    trackable = occurrence.trackable
    hours = occurrence.minutes_overdue // 60
    lateness = f"{hours}h late" if hours else f"{occurrence.minutes_overdue}m late"

    if audience == "house":
        notify_house(
            title=f"Still not done: {trackable.title}",
            body=(f"{trackable.owner.name} was due to do this "
                  f"{lateness}. Level {level} escalation."),
            severity=severity, app_slug=trackable.app_slug,
            url=trackable.url or "/tracker/",
            dedupe_key=f"esc:{occurrence.uuid}:{level}",
            channels=channels,
        )
        return

    for member in recipients:
        is_owner = member == trackable.owner
        if is_owner:
            title = f"Overdue: {trackable.title}"
            body = f"This was due {lateness}."
        else:
            title = f"{trackable.owner.name} hasn't done: {trackable.title}"
            body = (f"Due {occurrence.due_at:%a %d %b %H:%M} — {lateness}. "
                    f"You're on the escalation list for {trackable.owner.name}.")
        notify(member, title=title, body=body, severity=severity,
               app_slug=trackable.app_slug, url=trackable.url or "/tracker/",
               dedupe_key=f"esc:{occurrence.uuid}:{level}:{member.pk}",
               channels=channels, occurrence=str(occurrence.uuid), level=level)


def close_expired_windows(limit: int = 500) -> dict:
    """Occurrences whose window has fully closed become MISSED, which is what the
    streak and 'reliability' numbers are built from."""
    now = timezone.now()
    expired = (Occurrence.objects
               .open()
               .filter(window_ends_at__isnull=False, window_ends_at__lt=now)
               .select_related("trackable", "trackable__owner")[:limit])

    missed = 0
    for occurrence in expired:
        occurrence.status = Occurrence.Status.MISSED
        occurrence.save(update_fields=["status", "updated_at"])
        item_missed.send(sender=Occurrence, item=occurrence,
                         member=occurrence.trackable.owner, due_at=occurrence.due_at)
        missed += 1

    if missed:
        logger.info("Closed %s expired occurrence windows as missed", missed)
    return {"missed": missed}
