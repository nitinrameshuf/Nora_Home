"""
Search's filtering (docs/Main_App/subsystems/todo.md §7): full text across
titles, descriptions and comments, combinable with label / priority / owner /
state / date range / overdue.

One function, `search_tasks()`, is the whole surface. The view builds a
`FilterParams` from the querystring and a `SavedFilter.params` dict feed the
exact same function, so there is only ever one place that decides what a
filter means — a saved search behaving differently from the form that
produced it would be the kind of drift this module exists to prevent.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from django.db.models import Q
from django.utils import timezone

from nora_home.todo.models import InstanceOutcome

# Every key a saved filter or a querystring may carry. Anything outside this
# set (a stray param, a typo, an old saved filter from a removed field) is
# silently ignored rather than raising — a filter should degrade toward
# "shows too much" not "the page won't load."
FIELDS = ("q", "label", "priority", "owner_id", "state", "due_after", "due_before", "overdue")


@dataclass
class FilterParams:
    q: str = ""
    label: str = ""
    priority: str = ""
    owner_id: str = ""
    state: str = ""
    due_after: str = ""
    due_before: str = ""
    overdue: bool = False

    @classmethod
    def from_dict(cls, raw: dict) -> "FilterParams":
        kwargs = {k: raw[k] for k in FIELDS if k in raw and raw[k] not in (None, "")}
        if "overdue" in kwargs:
            kwargs["overdue"] = str(kwargs["overdue"]).lower() in ("1", "true", "on", "yes")
        return cls(**kwargs)

    def is_empty(self) -> bool:
        return not any(asdict(self).values())

    def as_dict(self) -> dict:
        """Only the fields actually set — what gets stored on a SavedFilter
        and what gets written back into a querystring, so neither carries a
        pile of empty keys."""
        return {k: v for k, v in asdict(self).items() if v}


def search_tasks(queryset, params: FilterParams):
    """Apply `params` on top of `queryset` — the caller supplies the starting
    set (already scoped to who may see it, via `api.tasks_for()`), this only
    ever narrows it further.

    `.distinct()` is required here for the same reason it is in `api.
    tasks_for()`: both the label join and the overdue-instance join can
    multiply a row, and a search result appearing twice reads as a bug in the
    query, not the join it actually is.
    """
    tasks = queryset

    if params.q:
        # A task's own comments (Task -> Comment) and an instance's comments
        # (Task -> Instance -> Comment) are two different join paths to the
        # same model, so this needs two traversals rather than one — but both
        # stay a single queryset filter, not a second query to feed back in.
        tasks = tasks.filter(
            Q(title__icontains=params.q) | Q(description__icontains=params.q)
            | Q(comments__body__icontains=params.q)
            | Q(instances__comments__body__icontains=params.q)
        )

    if params.label:
        tasks = tasks.filter(labels__name=params.label)
    if params.priority:
        tasks = tasks.filter(priority=params.priority)
    if params.owner_id:
        tasks = tasks.filter(owner_id=params.owner_id)
    if params.state:
        tasks = tasks.filter(state=params.state)
    if params.due_after:
        tasks = tasks.filter(due_on__gte=params.due_after)
    if params.due_before:
        tasks = tasks.filter(due_on__lte=params.due_before)
    if params.overdue:
        tasks = tasks.filter(instances__outcome=InstanceOutcome.PENDING,
                             instances__due_at__lt=timezone.now())

    return tasks.distinct()
