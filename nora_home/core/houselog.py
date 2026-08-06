"""
The House log — one timeline of what actually happened here.

Five subsystems each keep their own record of their own work, in their own
table, in their own shape. This module is the only place they are read as one
thing: audit events, system health, notifications the house sent, deliveries
that failed, integration runs, and telemetry readings that crossed a threshold.

## The rule this page is built on: record what *changed*, not what *ran*

That is not a stylistic preference, it is what makes the page readable at all.
Measured on the real house before this was written, over seven days:

    system health snapshots   563   of which 0 were unhealthy
    integration runs          275   of which 1 failed
    notifications sent          4
    deliveries                  4   of which 2 failed
    audit events                0   (Story 40 §12.3 is what fixes that)

A timeline that listed all 563 health snapshots would be 563 rows saying
"everything is fine", and the one row that mattered would be unfindable. So each
source is filtered to its own idea of an event:

    audit           every row — `record()` is only called where it matters, so
                    the curation already happened at the call site
    health          transitions only: the moment the house went degraded, and
                    the moment it recovered. A run of identical snapshots is
                    one event, not eighty a day
    integrations    failures, and the first success after a failure
    notifications   every one — the house decided to interrupt a person, which
                    is by definition an event
    deliveries      failed and skipped only. A delivery that worked is not
                    something that happened, it is the absence of something
                    happening; the notification row above already says the house
                    sent it
    telemetry       readings outside their series' warn/alert bounds

## Why the merge happens in Python

These five tables share no columns, no primary key space, and no severity
vocabulary, so there is no SQL UNION to write. Each source is queried with the
same window and the same cap, then merged and re-truncated. The cost of that is
bounded by `limit * number of sources` rows, not by the size of the tables.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from django.db.models import Q
from django.utils import timezone

# Ordered from quietest to loudest. The severity filter is a *floor* — picking
# "warning" means "warning and worse", which is the question someone actually
# has ("what went wrong this week"), rather than an exact match nobody wants.
SEVERITY_ORDER = ["debug", "info", "notice", "nudge", "warning", "alert", "critical"]

SOURCES = {
    "audit": "Actions",
    "health": "System health",
    "notifications": "Alerts sent",
    "deliveries": "Delivery failures",
    "integrations": "Integrations",
    "telemetry": "Measurements",
}

DEFAULT_DAYS = 7
DEFAULT_LIMIT = 200


@dataclass(frozen=True)
class LogEntry:
    """One thing that happened, in the vocabulary the page speaks.

    Every source is flattened into this before merging, so the template renders
    one shape and knows nothing about which table a row came from.
    """

    at: datetime
    source: str          # a key of SOURCES
    severity: str        # a value from SEVERITY_ORDER
    title: str
    detail: str = ""
    actor: str = ""
    app_slug: str = ""
    url: str = ""
    facts: dict = field(default_factory=dict)

    @property
    def source_label(self) -> str:
        return SOURCES.get(self.source, self.source)

    @property
    def is_loud(self) -> bool:
        """Whether this deserves visual weight. Used by the template rather than
        it re-deriving the severity ladder in template syntax."""
        return self.severity in ("warning", "alert", "critical")


def severity_at_least(minimum: str) -> list[str]:
    """Every severity from `minimum` upwards. Unknown input means no filter —
    a hand-typed query string must not silently empty the page."""
    if minimum not in SEVERITY_ORDER:
        return list(SEVERITY_ORDER)
    return SEVERITY_ORDER[SEVERITY_ORDER.index(minimum):]


def timeline(*, since=None, until=None, sources=None, severity: str = "",
             query: str = "", limit: int = DEFAULT_LIMIT) -> list[LogEntry]:
    """Every entry in the window, newest first.

    Each collector is called inside its own try/except: one subsystem's table
    being missing or its app uninstalled must degrade to a shorter timeline, not
    a 500 on the page a person opens *because* something is wrong (CLAUDE.md §6,
    "failures degrade, never cascade").
    """
    since = since or timezone.now() - timedelta(days=DEFAULT_DAYS)
    until = until or timezone.now()
    wanted = set(sources) if sources else set(SOURCES)
    allowed = set(severity_at_least(severity)) if severity else None

    collectors = {
        "audit": _audit_entries,
        "health": _health_entries,
        "notifications": _notification_entries,
        "deliveries": _delivery_entries,
        "integrations": _integration_entries,
        "telemetry": _telemetry_entries,
    }

    entries: list[LogEntry] = []
    for key, collect in collectors.items():
        if key not in wanted:
            continue
        try:
            entries.extend(collect(since, until, limit))
        except Exception:  # noqa: BLE001 — see the docstring
            import logging

            logging.getLogger(__name__).exception(
                "House log source %r failed; showing the rest", key)

    if allowed is not None:
        entries = [e for e in entries if e.severity in allowed]
    if query:
        needle = query.casefold()
        entries = [e for e in entries
                   if needle in e.title.casefold()
                   or needle in e.detail.casefold()
                   or needle in e.actor.casefold()]

    entries.sort(key=lambda e: e.at, reverse=True)
    return entries[:limit]


# ── sources ──────────────────────────────────────────────────────────────────

def _audit_entries(since, until, limit) -> list[LogEntry]:
    from nora_home.core.models import AuditEvent

    rows = (AuditEvent.objects
            .filter(created_at__gte=since, created_at__lte=until)
            .select_related("actor")[:limit])
    return [
        LogEntry(
            at=row.created_at,
            source="audit",
            severity=row.severity,
            title=row.subject or row.action,
            # The action is the machine-readable half and the subject the human
            # one; showing the action as detail means a row is still legible
            # when whoever called record() gave it no subject.
            detail=row.action,
            actor=row.actor.name if row.actor else "",
            app_slug=row.app_slug,
            facts=row.detail if isinstance(row.detail, dict) else {},
        )
        for row in rows
    ]


def _health_entries(since, until, limit) -> list[LogEntry]:
    """Only the moments the answer changed.

    One extra snapshot is fetched from *before* the window, so a transition that
    happened at the very start of it is still recognised as a transition rather
    than being reported as the house's first-ever state.
    """
    from nora_home.core.models import SystemHealthSnapshot

    snapshots = list(
        SystemHealthSnapshot.objects
        .filter(created_at__gte=since, created_at__lte=until)
        .order_by("created_at")
        .only("created_at", "healthy", "services")
    )
    if not snapshots:
        return []

    previous = (SystemHealthSnapshot.objects
                .filter(created_at__lt=since)
                .order_by("-created_at")
                .only("healthy")
                .first())
    was_healthy = previous.healthy if previous else snapshots[0].healthy

    entries = []
    for snapshot in snapshots:
        if snapshot.healthy == was_healthy:
            continue
        was_healthy = snapshot.healthy
        troubled = sorted(
            name for name, probe in (snapshot.services or {}).items()
            if isinstance(probe, dict) and probe.get("status") not in (None, "ok")
        )
        entries.append(LogEntry(
            at=snapshot.created_at,
            source="health",
            severity="info" if snapshot.healthy else "alert",
            title="The house recovered" if snapshot.healthy else "The house went degraded",
            detail=", ".join(troubled) if troubled else "",
            app_slug="core",
        ))
    return entries[-limit:]


def _notification_entries(since, until, limit) -> list[LogEntry]:
    from nora_home.notifications.models import Notification

    rows = (Notification.objects
            .filter(created_at__gte=since, created_at__lte=until)
            .select_related("recipient")[:limit])
    return [
        LogEntry(
            at=row.created_at,
            source="notifications",
            severity=row.severity,
            title=row.title,
            detail=row.body[:200],
            # Null recipient means the whole house — saying so is more useful
            # than an empty cell, which reads as "we don't know".
            actor=row.recipient.name if row.recipient else "everyone",
            app_slug=row.app_slug,
            url=row.url,
        )
        for row in rows
    ]


def _delivery_entries(since, until, limit) -> list[LogEntry]:
    from nora_home.notifications.models import Delivery

    rows = (Delivery.objects
            .filter(created_at__gte=since, created_at__lte=until,
                    status__in=[Delivery.Status.FAILED, Delivery.Status.SKIPPED])
            .select_related("notification")[:limit])
    return [
        LogEntry(
            at=row.created_at,
            source="deliveries",
            # A skip is a decision the house made (quiet hours, no address on
            # file); a failure is the house trying and not managing it. Only the
            # second one is a problem, and they must not look alike.
            severity="alert" if row.status == Delivery.Status.FAILED else "notice",
            title=f"{row.channel} {row.get_status_display().lower()}: "
                  f"{row.notification.title}",
            detail=row.error[:200],
            actor=row.target,
            app_slug=row.notification.app_slug,
        )
        for row in rows
    ]


def _integration_entries(since, until, limit) -> list[LogEntry]:
    """Failures, and the recovery that ends each one.

    A healthy integration polling every fifteen minutes writes ninety-six rows a
    day that all say the same thing. What someone wants from this page is the
    two rows where it stopped and started working again.
    """
    from nora_home.integrations.models import IntegrationRun

    runs = list(
        IntegrationRun.objects
        .filter(created_at__gte=since, created_at__lte=until)
        .select_related("integration")
        .order_by("created_at")
    )

    failing: set[int] = set()
    entries = []
    for run in runs:
        if not run.succeeded:
            # Only the first failure of an episode: an integration down all week
            # is one thing that happened, not six hundred.
            if run.integration_id not in failing:
                failing.add(run.integration_id)
                entries.append(LogEntry(
                    at=run.created_at, source="integrations", severity="warning",
                    title=f"{run.integration.name} started failing",
                    detail=run.error[:200], app_slug="integrations",
                ))
        elif run.integration_id in failing:
            failing.discard(run.integration_id)
            entries.append(LogEntry(
                at=run.created_at, source="integrations", severity="info",
                title=f"{run.integration.name} recovered",
                detail=f"succeeded in {run.duration_ms} ms", app_slug="integrations",
            ))
    return entries[-limit:]


def _telemetry_entries(since, until, limit) -> list[LogEntry]:
    """Readings outside their series' own bounds.

    Expressed as a database filter against the series' thresholds rather than by
    calling `Series.classify()` over every reading in Python — the readings table
    is the one in this house designed to get large.
    """
    from django.db.models import F

    from nora_home.telemetry.models import Reading

    breached = (
        Q(series__alert_below__isnull=False, value__lt=F("series__alert_below"))
        | Q(series__alert_above__isnull=False, value__gt=F("series__alert_above"))
        | Q(series__warn_below__isnull=False, value__lt=F("series__warn_below"))
        | Q(series__warn_above__isnull=False, value__gt=F("series__warn_above"))
    )
    rows = (Reading.objects
            .filter(recorded_at__gte=since, recorded_at__lte=until)
            .filter(breached)
            .select_related("series")[:limit])

    entries = []
    for row in rows:
        status = row.series.classify(row.value)
        if status == "ok":  # defensive: the filter and classify() must agree
            continue
        entries.append(LogEntry(
            at=row.recorded_at,
            source="telemetry",
            severity="alert" if status == "alert" else "warning",
            title=f"{row.series.label}: "
                  f"{row.value:.{row.series.precision}f}{row.series.unit}",
            detail=f"outside the {status} threshold",
            app_slug=row.series.app_slug,
            facts={"series": row.series.key, "value": row.value},
        ))
    return entries


# ── charts ───────────────────────────────────────────────────────────────────

def charts(entries: list[LogEntry], *, since, until) -> dict:
    """One ECharts option per chart, or `None` where there is nothing to draw.

    `None` is the signal the template renders as a sentence — the same contract
    Todo's Reporting page uses, and for the same reason: an empty chart with real
    axes claims to have measured something.
    """
    if not entries:
        return {"activity": None, "mix": None}

    days = _day_range(since, until)
    per_source = {key: [0] * len(days) for key in SOURCES}
    index = {day: i for i, day in enumerate(days)}

    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry.severity] = counts.get(entry.severity, 0) + 1
        slot = index.get(timezone.localtime(entry.at).date().isoformat())
        if slot is not None:
            per_source[entry.source][slot] += 1

    used = [key for key in SOURCES if any(per_source[key])]

    return {
        "activity": {
            "tooltip": {"trigger": "axis"},
            "legend": {"data": [SOURCES[key] for key in used]},
            "xAxis": {"type": "category", "data": [d[5:] for d in days]},
            "yAxis": {"type": "value", "name": "entries"},
            "series": [
                {"name": SOURCES[key], "type": "bar", "stack": "all",
                 "data": per_source[key]}
                for key in used
            ],
        } if used else None,
        # Severity order, not count order: this reads as a ladder, and sorting it
        # by size would put "info" first on a quiet week and "alert" first on a
        # bad one, so the same chart would mean two different things.
        "mix": {
            "tooltip": {"trigger": "axis"},
            "xAxis": {"type": "category",
                      "data": [s for s in SEVERITY_ORDER if counts.get(s)]},
            "yAxis": {"type": "value", "name": "entries"},
            "series": [{"type": "bar",
                        "data": [counts[s] for s in SEVERITY_ORDER if counts.get(s)]}],
        } if counts else None,
    }


def _day_range(since, until) -> list[str]:
    start = timezone.localtime(since).date()
    end = timezone.localtime(until).date()
    return [(start + timedelta(days=n)).isoformat()
            for n in range((end - start).days + 1)]
