"""
Todo's data model. See docs/Main_App/subsystems/todo.md §3 for the design this
implements field-for-field, and §13 for the rule every model here is built
around: **no counter fields**. Nothing here caches a count, a rate, or a streak
— every statistic the app shows is computed from Instance/ChangeEvent history on
read (nora_home.todo.analytics, added in a later phase), because history is
retroactively editable and a cached number silently goes wrong the moment
someone corrects a day three weeks back.

Task is the thing and its rule — one row, one card on the board. Instance is one
dated occasion of it; a one-shot task has exactly one, a recurring task
accumulates one per occurrence, forever. That split is what makes the history
(and every chart drawn from it) possible.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models

from nora_home.core.models import OwnedModel, SoftDeleteModel, TimeStampedModel, UUIDModel


class Priority(models.IntegerChoices):
    P1 = 1, "Priority 1"
    P2 = 2, "Priority 2"
    P3 = 3, "Priority 3"


class TaskState(models.TextChoices):
    OPEN = "open", "Open"
    ARCHIVED = "archived", "Archived"  # "not now" — quiet, not done. See §4.
    DONE = "done", "Done"


class TaskSource(models.TextChoices):
    USER = "user", "A person"
    SYSTEM = "system", "Nora Home"  # decides which board it appears on — §2


class RecurrenceType(models.TextChoices):
    NONE = "none", "One time"
    FIXED = "fixed", "Fixed"      # "every Monday" — independent of completion
    ROLLING = "rolling", "Rolling"  # "N days after I last did it"


class AlarmKind(models.TextChoices):
    CHIME = "chime", "Chime"
    FILE = "file", "Audio file"
    SPEECH = "speech", "Spoken text"


class Task(UUIDModel, OwnedModel, SoftDeleteModel):
    """The thing, and its rule. `OwnedModel` gives `owner` — required, not
    nullable: every task, including a system one, has an owner (see
    docs/Main_App/subsystems/todo.md §3's "Notes that matter"). The owner may
    differ from whoever created it — anyone can put a task on anyone's board."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)  # plain text, deliberately — §3

    # No default: the create form must not pre-select a column for you.
    priority = models.PositiveSmallIntegerField(choices=Priority.choices)

    labels = models.ManyToManyField("todo.Label", blank=True, related_name="tasks")

    # Who *can do it*, as against `owner` — who is *responsible*. Kept separate
    # so escalation still has exactly one person to chase (§4a), which is what
    # keeps the ladder meaningful, while the work itself can belong to several.
    # Any one assignee closes it; there is no "everyone must tick it".
    assignees = models.ManyToManyField(settings.AUTH_USER_MODEL, blank=True,
                                       related_name="todo_assigned_tasks")
    # **Its presence is the approval requirement** — there is deliberately no
    # separate mode flag, because two fields meaning one thing is two fields to
    # keep in sync. Non-recurring tasks only; see clean() and Meta.constraints.
    approver = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                 on_delete=models.SET_NULL,
                                 related_name="todo_tasks_to_approve")

    source = models.CharField(max_length=6, choices=TaskSource.choices,
                              default=TaskSource.USER)

    due_on = models.DateField(null=True, blank=True)
    due_time = models.TimeField(null=True, blank=True)
    # Whether due_on can move. Load-bearing for the scheduling recommendations
    # in §11 — a suggestion engine cannot tell what is safe to shift without it.
    deadline_firm = models.BooleanField(default=False)

    planned_minutes = models.PositiveIntegerField(null=True, blank=True)

    recurrence_type = models.CharField(max_length=7, choices=RecurrenceType.choices,
                                       default=RecurrenceType.NONE)
    # Meaning depends on recurrence_type — a weekday set for FIXED, an interval
    # in days for ROLLING. Interpreted by nora_home.todo.recurrence (Story 30).
    recurrence_spec = models.JSONField(default=dict, blank=True)

    state = models.CharField(max_length=8, choices=TaskState.choices,
                             default=TaskState.OPEN, db_index=True)

    escalation_enabled = models.BooleanField(default=False)
    # String reference, not a Python import: EscalationPolicy still lives on
    # the tracker (Level 1) until Story 40 deletes it and gives Todo its own.
    # A FK must name a real model, but a string reference defers resolution
    # until Django's app registry is ready, so this needs no
    # `from nora_home.tracker.models import ...` anywhere in this file.
    escalation_policy = models.ForeignKey(
        "tracker.EscalationPolicy", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="+")

    # Per task, not per reminder — confirmed 2026-08-05. alarm_ref's meaning
    # depends on alarm_kind: a built-in chime's name, an object-storage key for
    # an uploaded file, or the text to speak. The actual playback plumbing is
    # Story 38 (Alarms & House Audio); this just holds the choice.
    alarm_kind = models.CharField(max_length=6, choices=AlarmKind.choices, blank=True)
    alarm_ref = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["priority", "-created_at"]
        indexes = [
            models.Index(fields=["state", "priority"]),
            models.Index(fields=["source", "state"]),
        ]
        constraints = [
            # Both here and in clean(), on purpose. A rule that lives only in
            # application code is a rule that a management command, a data
            # import, or an admin bulk edit will quietly break — and the damage
            # here is an approval queue nobody keeps up with, which teaches
            # everyone to rubber-stamp.
            models.CheckConstraint(
                condition=(
                    models.Q(approver__isnull=True)
                    | models.Q(recurrence_type=RecurrenceType.NONE)
                ),
                name="todo_no_approver_on_recurring",
            ),
        ]

    def __str__(self):
        return self.title

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.approver_id and self.is_recurring:
            raise ValidationError({"approver": (
                "A recurring task cannot have an approver — every occurrence "
                "would need someone else's sign-off. If something genuinely "
                "needs checking every time, that is two tasks: one to do it, "
                "one to check it (see docs/Main_App/subsystems/todo.md §4a).")})

    @property
    def is_recurring(self) -> bool:
        return self.recurrence_type != RecurrenceType.NONE

    @property
    def needs_approval(self) -> bool:
        """Reads better at call sites than `task.approver_id is not None`, and
        keeps every one of them agreeing on what the requirement *is* — which
        matters precisely because there is no flag to point at."""
        return self.approver_id is not None


class InstanceOutcome(models.TextChoices):
    PENDING = "pending", "Pending"
    # The work is finished but the approver has not said yes yet (§4a). It is
    # **not** done: it leaves the board's open columns, but Reporting does not
    # count it as a completion, and it does not close a rolling recurrence.
    AWAITING_APPROVAL = "awaiting_approval", "Awaiting approval"
    DONE = "done", "Done"
    MISSED = "missed", "Missed"
    SKIPPED = "skipped", "Skipped"


class Instance(UUIDModel, TimeStampedModel):
    """One dated occasion of a Task. History is made of these — every
    statistic in analytics.py (added later) counts them, not Task itself."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="instances")
    due_at = models.DateTimeField(db_index=True)
    outcome = models.CharField(max_length=17, choices=InstanceOutcome.choices,
                               default=InstanceOutcome.PENDING, db_index=True)

    # Retroactively editable by design (§4) — completing last Monday's instance
    # on Wednesday must not touch Wednesday's own row.
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL,
                                     related_name="todo_completed_instances")
    actual_minutes = models.PositiveIntegerField(null=True, blank=True)
    note = models.TextField(blank=True)

    # Separate from completed_at/completed_by rather than reusing them: two
    # different people did two different things at two different moments, and
    # collapsing them would lose which of them actually did the work.
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="todo_approved_instances")

    # Set only when skipped before due_at (§5) — after that moment it is a
    # miss, and cannot be relabelled a skip retroactively. Enforced in clean();
    # not a DB constraint because it compares two fields conditionally, which
    # portable CheckConstraints across SQLite/MySQL make awkward.
    skipped_at = models.DateTimeField(null=True, blank=True)

    # Escalation bookkeeping. The ladder walks per-occasion — which rung it has
    # reached, and whether someone has said "seen it" — so this state belongs on
    # the instance, not the task. Deferred here from Story 29 deliberately:
    # §3's field list omits them, but §9 keeps escalation "largely intact", and
    # the ported engine has nowhere to write without them. The engine itself
    # arrives with the notification routing it depends on (§8's priority table),
    # so until then these are written by nothing and read by nothing.
    escalation_level = models.PositiveSmallIntegerField(default=0, db_index=True)
    last_escalated_at = models.DateTimeField(null=True, blank=True)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                        on_delete=models.SET_NULL,
                                        related_name="todo_acknowledged_instances")

    class Meta:
        ordering = ["due_at"]
        indexes = [models.Index(fields=["task", "outcome", "due_at"])]

    def __str__(self):
        return f"{self.task.title} @ {self.due_at:%Y-%m-%d %H:%M}"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.skipped_at and self.skipped_at > self.due_at:
            raise ValidationError(
                "skipped_at must be before due_at — after the moment passes it "
                "is a miss, not a skip (see docs/Main_App/subsystems/todo.md §5)")

    @property
    def effective_minutes(self) -> int | None:
        """What it took, or what it was expected to take. The fallback is what
        lets the load calculation work before anyone has recorded real times."""
        return self.actual_minutes if self.actual_minutes is not None else self.task.planned_minutes


class EventRecurrence(models.TextChoices):
    NONE = "none", "One time"
    YEARLY = "yearly", "Every year"


class Event(UUIDModel, SoftDeleteModel, TimeStampedModel):
    """Consumes time; is not work — a birthday, an appointment, an exam. Never
    on the priority board, only the Calendar. Owner is nullable (unlike Task's)
    — None means the event belongs to the house, not a person."""

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="todo_events")

    starts_at = models.DateTimeField()
    all_day = models.BooleanField(default=False)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)

    recurrence = models.CharField(max_length=6, choices=EventRecurrence.choices,
                                  default=EventRecurrence.NONE)
    labels = models.ManyToManyField("todo.Label", blank=True, related_name="events")

    class Meta:
        ordering = ["starts_at"]
        indexes = [models.Index(fields=["starts_at"])]

    def __str__(self):
        return self.title


class Label(TimeStampedModel):
    """House-wide, user-created — a task carries several. No second container
    concept (no projects, no folders); confirmed 2026-08-05."""

    name = models.CharField(max_length=60, unique=True)
    colour = models.CharField(max_length=7, blank=True)  # "#7dd3fc"

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Comment(TimeStampedModel):
    """Attaches to a Task or an Instance — task-level for standing context,
    instance-level for a note about one occasion (§4)."""

    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE,
                             related_name="comments")
    instance = models.ForeignKey(Instance, null=True, blank=True, on_delete=models.CASCADE,
                                 related_name="comments")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                               related_name="todo_comments")
    body = models.TextField()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(task__isnull=False, instance__isnull=True)
                    | models.Q(task__isnull=True, instance__isnull=False)
                ),
                name="todo_comment_exactly_one_parent",
            ),
        ]

    def __str__(self):
        return f"comment by {self.author} on {self.task_id or self.instance_id}"


class Attachment(TimeStampedModel):
    """A photo, in object storage. Attaches to a Task, an Instance, or an
    Event — Event is the one addition beyond §3's "task or instance" framing,
    needed because Event's own description explicitly lists "attachments" as
    something it has, with no other model to hold them. Optional at every
    level: object storage is down, the task still saves (ground rule 5)."""

    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE,
                             related_name="attachments")
    instance = models.ForeignKey(Instance, null=True, blank=True, on_delete=models.CASCADE,
                                 related_name="attachments")
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.CASCADE,
                              related_name="attachments")
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                    on_delete=models.SET_NULL,
                                    related_name="todo_attachments")
    image = models.ImageField(upload_to="todo/attachments/%Y/%m/")
    caption = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(task__isnull=False, instance__isnull=True, event__isnull=True)
                    | models.Q(task__isnull=True, instance__isnull=False, event__isnull=True)
                    | models.Q(task__isnull=True, instance__isnull=True, event__isnull=False)
                ),
                name="todo_attachment_exactly_one_parent",
            ),
        ]

    def __str__(self):
        return self.caption or f"attachment on {self.task_id or self.instance_id or self.event_id}"


class Link(TimeStampedModel):
    """External URL, or an internal path into the house — a task can point at
    another app's page, another task, or a Reporting view. Attaches to a Task
    or an Instance, matching §3's "Comment · Attachment · Link" framing (Event
    does not list links among what it holds, unlike attachments)."""

    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE,
                             related_name="links")
    instance = models.ForeignKey(Instance, null=True, blank=True, on_delete=models.CASCADE,
                                 related_name="links")
    label = models.CharField(max_length=200, blank=True,
                             help_text="Display text. For an internal path, the "
                                       "real name of what it points at — resolved "
                                       "at render time, not stored stale here.")
    url = models.CharField(max_length=500)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(task__isnull=False, instance__isnull=True)
                    | models.Q(task__isnull=True, instance__isnull=False)
                ),
                name="todo_link_exactly_one_parent",
            ),
        ]

    def __str__(self):
        return self.label or self.url

    @property
    def is_internal(self) -> bool:
        return self.url.startswith("/")


class ReminderChannel(models.TextChoices):
    SLACK = "slack", "Slack"
    SOUND = "sound", "Sound"
    INAPP = "inapp", "In-app"
    DISPLAY = "display", "Wall banner"


class Reminder(TimeStampedModel):
    """Belongs to a Task or an Event; fires for every instance/occurrence of
    it. Relative offsets everywhere; absolute times only make sense on a
    non-recurring task — enforced where reminders are actually scheduled
    (a later phase), not here, since it depends on the task's own recurrence
    state at read time, not something a DB constraint can see."""

    task = models.ForeignKey(Task, null=True, blank=True, on_delete=models.CASCADE,
                             related_name="reminders")
    event = models.ForeignKey(Event, null=True, blank=True, on_delete=models.CASCADE,
                              related_name="reminders")

    offset_minutes = models.IntegerField(
        null=True, blank=True,
        help_text="Minutes before the due moment. Negative would be after.")
    absolute_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Non-recurring tasks only — see the class docstring.")
    channels = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(task__isnull=False, event__isnull=True)
                    | models.Q(task__isnull=True, event__isnull=False)
                ),
                name="todo_reminder_exactly_one_parent",
            ),
        ]

    def __str__(self):
        return f"reminder on {self.task_id or self.event_id}"


class ChangeEvent(TimeStampedModel):
    """The most important table for the future, and the cheapest to get
    wrong (§3, §13). Every reschedule, priority change, label change, skip,
    and archive is its own dated row — never a counter. `created_at`
    (inherited) is the "when"; there is no separate `at` field, since a
    duplicate timestamp on an already-immutable row would just be two sources
    of truth for one fact."""

    task = models.ForeignKey(Task, on_delete=models.CASCADE, related_name="changes")
    instance = models.ForeignKey(Instance, null=True, blank=True, on_delete=models.CASCADE,
                                 related_name="changes")
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                              on_delete=models.SET_NULL, related_name="todo_changes")

    field = models.CharField(max_length=40)
    from_value = models.JSONField(null=True, blank=True)
    to_value = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["task", "field", "-created_at"])]

    def __str__(self):
        return f"{self.task_id}: {self.field} -> {self.to_value!r}"


class Tone(models.TextChoices):
    CALM = "calm", "Calm"
    STANDARD = "standard", "Standard"
    COMPETITIVE = "competitive", "Competitive"


class TodoPreference(TimeStampedModel):
    """Per-member settings, owned by this subsystem — rendered on Todo's own
    settings page (/todo/settings/), not the platform Settings page. Fields
    are the two already specified elsewhere in the design doc: the default due
    hour for date-only tasks (§8) and the Reporting tone preset (§10)."""

    member = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                  related_name="todo_preference")
    default_due_hour = models.PositiveSmallIntegerField(
        default=9,
        help_text="Local hour a date-only task falls due, when nothing more "
                  "specific is set.")
    tone = models.CharField(max_length=11, choices=Tone.choices, default=Tone.STANDARD)

    def __str__(self):
        return f"Todo preferences for {self.member}"
