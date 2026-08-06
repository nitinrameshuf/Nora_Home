"""
Slack's inbound half (docs/Main_App/subsystems/todo.md §12): the dispatch
registry, `/todo` and its subcommands, the message buttons, and the Block Kit
those buttons are rendered from.

Nothing here touches the network. The socket itself is three lines of slack_sdk
wiring; everything this house actually *decides* lives in `reply_for()` and the
handlers, against plain dicts — which is why those are split out from the
connection in the first place.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.utils import timezone

from nora_home.notifications import slack_socket
from nora_home.notifications.channels.slack import SlackChannel
from nora_home.notifications.models import Notification
from nora_home.notifications.slack_commands import (
    UNKNOWN_MEMBER,
    dispatch_action,
    dispatch_command,
    member_for,
    registered_actions,
    registered_commands,
)
from nora_home.todo import slack_commands as todo_slack
from nora_home.todo.models import (
    Instance,
    InstanceOutcome,
    Priority,
    Reminder,
    Task,
    TaskState,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def slack_member(make_member):
    member = make_member("nitin", role="admin")
    member.slack_user_id = "U0NITIN"
    member.save(update_fields=["slack_user_id"])
    return member


@pytest.fixture
def make_task(slack_member):
    def _make(**kwargs):
        kwargs.setdefault("title", "Take the bins out")
        kwargs.setdefault("owner", slack_member)
        kwargs.setdefault("priority", Priority.P2)
        return Task.objects.create(**kwargs)
    return _make


@pytest.fixture
def due_instance(make_task):
    """A task with one pending occasion, already due."""
    def _make(**kwargs):
        task = make_task(**kwargs)
        return Instance.objects.create(
            task=task, due_at=timezone.now() - timedelta(hours=1))
    return _make


# ── the registry ─────────────────────────────────────────────────────────────

def test_todo_registers_itself_on_app_ready():
    """TodoConfig.ready() imports the module; if that import is ever dropped,
    every command silently becomes "not a command this house knows"."""
    assert "/todo" in registered_commands()
    assert {"todo_done", "todo_skip", "todo_snooze", "todo_reassign"} <= set(
        registered_actions())


def test_an_unmapped_slack_account_is_told_what_to_do(db):
    """Never act on a guess: a Slack display name is not an identity, and
    completing the wrong person's task is the failure being avoided."""
    reply = dispatch_command("/todo", "list", "U0STRANGER")

    assert reply == UNKNOWN_MEMBER


def test_member_for_ignores_deactivated_people(slack_member):
    slack_member.is_active = False
    slack_member.save(update_fields=["is_active"])

    assert member_for("U0NITIN") is None


def test_an_unknown_command_does_not_pretend_to_work(slack_member):
    assert "isn't a command" in dispatch_command("/nope", "", "U0NITIN")


def test_a_handler_that_raises_becomes_an_apology_not_a_silence(slack_member, monkeypatch):
    """A button that does nothing at all is the worst outcome on a phone —
    there is no way to tell it failed from it being slow."""
    def boom(member, text):
        raise RuntimeError("kaboom")

    monkeypatch.setitem(
        __import__("nora_home.notifications.slack_commands", fromlist=["_COMMANDS"])._COMMANDS,
        "/todo", boom)

    reply = dispatch_command("/todo", "list", "U0NITIN")

    assert "went wrong" in reply


# ── /todo subcommands ────────────────────────────────────────────────────────

def test_a_bare_slash_todo_lists(slack_member, due_instance):
    due_instance()

    reply = dispatch_command("/todo", "", "U0NITIN")

    assert "Take the bins out" in reply


def test_list_marks_what_is_overdue(slack_member, due_instance):
    due_instance()

    assert "overdue" in dispatch_command("/todo", "list", "U0NITIN")


def test_list_says_so_plainly_when_there_is_nothing(slack_member):
    assert "Nothing open" in dispatch_command("/todo", "list", "U0NITIN")


def test_help_is_offered_for_an_unknown_subcommand(slack_member):
    reply = dispatch_command("/todo", "frobnicate", "U0NITIN")

    assert "don't know" in reply
    assert "/todo new" in reply


def test_new_creates_a_task_on_the_senders_board(slack_member):
    reply = dispatch_command("/todo", "new Water the plants", "U0NITIN")

    task = Task.objects.get(title="Water the plants")
    assert task.owner == slack_member
    assert task.priority == Priority.P2
    assert "Water the plants" in reply


def test_new_invents_no_due_date(slack_member):
    """§3: a fabricated deadline would land in the history every chart is drawn
    from. Undated tasks live on the board perfectly well."""
    dispatch_command("/todo", "new Water the plants", "U0NITIN")

    assert Task.objects.get(title="Water the plants").due_on is None


def test_new_without_a_title_asks_for_one(slack_member):
    reply = dispatch_command("/todo", "new", "U0NITIN")

    assert "What should it be called" in reply
    assert not Task.objects.exists()


def test_add_is_accepted_as_a_synonym_for_new(slack_member):
    dispatch_command("/todo", "add Buy milk", "U0NITIN")

    assert Task.objects.filter(title="Buy milk").exists()


def test_ack_stops_the_ladder_without_claiming_the_work_is_done(slack_member, due_instance):
    instance = due_instance()

    reply = dispatch_command("/todo", "ack", "U0NITIN")

    instance.refresh_from_db()
    assert instance.acknowledged_by == slack_member
    assert instance.outcome == InstanceOutcome.PENDING  # still open, deliberately
    assert "stays open" in reply


def test_ack_with_nothing_overdue_says_so(slack_member, make_task):
    task = make_task()
    Instance.objects.create(task=task, due_at=timezone.now() + timedelta(days=1))

    assert "Nothing overdue" in dispatch_command("/todo", "ack", "U0NITIN")


# ── approval, from a phone ───────────────────────────────────────────────────

@pytest.fixture
def awaiting_my_approval(make_member, slack_member):
    """Someone else's task, waiting on `slack_member` to approve it."""
    kid = make_member("kid")
    task = Task.objects.create(title="Tidy your room", owner=kid,
                               priority=Priority.P2, approver=slack_member)
    return Instance.objects.create(
        task=task, due_at=timezone.now() - timedelta(hours=1),
        outcome=InstanceOutcome.AWAITING_APPROVAL,
        completed_at=timezone.now(), completed_by=kid)


def test_approve_approves_the_oldest_thing_waiting_on_you(slack_member,
                                                          awaiting_my_approval):
    reply = dispatch_command("/todo", "approve", "U0NITIN")

    awaiting_my_approval.refresh_from_db()
    assert awaiting_my_approval.outcome == InstanceOutcome.DONE
    assert "Tidy your room" in reply


def test_approve_with_nothing_waiting_says_so(slack_member):
    assert "Nothing is waiting" in dispatch_command("/todo", "approve", "U0NITIN")


def test_reject_requires_a_reason(slack_member, awaiting_my_approval):
    """§4a makes the reason mandatory, and a slash command is the one place
    someone could plausibly try to skip it."""
    reply = dispatch_command("/todo", "reject", "U0NITIN")

    awaiting_my_approval.refresh_from_db()
    assert awaiting_my_approval.outcome == InstanceOutcome.AWAITING_APPROVAL
    assert "needs a reason" in reply


def test_reject_sends_it_back_with_the_reason(slack_member, awaiting_my_approval):
    reply = dispatch_command("/todo", "reject not properly cleaned", "U0NITIN")

    awaiting_my_approval.refresh_from_db()
    assert awaiting_my_approval.outcome == InstanceOutcome.PENDING
    assert "not properly cleaned" in reply


def test_you_cannot_approve_someone_elses_queue(make_member, slack_member):
    """The api's permission check is the one that matters; Slack must not be a
    back door around it."""
    other = make_member("partner", role="adult")
    task = Task.objects.create(title="Not yours", owner=make_member("kid"),
                               priority=Priority.P2, approver=other)
    Instance.objects.create(task=task, due_at=timezone.now(),
                            outcome=InstanceOutcome.AWAITING_APPROVAL)

    assert "Nothing is waiting" in dispatch_command("/todo", "approve", "U0NITIN")


# ── the buttons ──────────────────────────────────────────────────────────────

def test_done_completes_the_occasion(slack_member, due_instance):
    instance = due_instance()

    reply = dispatch_action("todo_done", str(instance.uuid), "U0NITIN")

    instance.refresh_from_db()
    assert instance.outcome == InstanceOutcome.DONE
    assert instance.completed_by == slack_member
    assert "done" in reply.lower()


def test_done_on_a_task_needing_approval_says_where_it_went(make_member, slack_member):
    approver = make_member("partner", role="adult")
    task = Task.objects.create(title="Tidy up", owner=slack_member,
                               priority=Priority.P2, approver=approver)
    instance = Instance.objects.create(task=task, due_at=timezone.now())

    reply = dispatch_action("todo_done", str(instance.uuid), "U0NITIN")

    instance.refresh_from_db()
    assert instance.outcome == InstanceOutcome.AWAITING_APPROVAL
    assert approver.name in reply


def test_skip_is_worded_as_a_decision_not_a_failure(slack_member, make_task):
    """§5: a skip declared before the due moment is a deliberate decision and is
    excluded from miss patterns. The button sits next to Done and should not
    feel like an admission."""
    task = make_task()
    instance = Instance.objects.create(
        task=task, due_at=timezone.now() + timedelta(hours=1))

    reply = dispatch_action("todo_skip", str(instance.uuid), "U0NITIN")

    instance.refresh_from_db()
    assert instance.outcome == InstanceOutcome.SKIPPED
    assert "not a miss" in reply


def test_skipping_after_the_due_moment_is_refused(slack_member, due_instance):
    """Not a bug in the button — §5's actual rule. Once the moment has passed
    the occasion is a miss, and calling it a skip would launder a miss out of
    the pattern data Reporting is built on."""
    instance = due_instance()

    reply = dispatch_action("todo_skip", str(instance.uuid), "U0NITIN")

    instance.refresh_from_db()
    assert instance.outcome == InstanceOutcome.PENDING
    assert "miss" in reply


def test_snooze_re_reminds_without_moving_the_deadline(slack_member, due_instance):
    """Moving due_on would write a deferral into the trail
    `analytics.deferral_by_label()` reads — "remind me after dinner" is not the
    same claim as "this is due tomorrow"."""
    instance = due_instance()
    original_due = instance.task.due_on

    reply = dispatch_action("todo_snooze", str(instance.uuid), "U0NITIN")

    instance.task.refresh_from_db()
    assert instance.task.due_on == original_due
    assert Reminder.objects.filter(task=instance.task,
                                   absolute_at__isnull=False).exists()
    assert "back at" in reply


def test_reassign_moves_the_owner_and_records_it(make_member, slack_member,
                                                 due_instance):
    partner = make_member("partner", role="adult")
    instance = due_instance()

    reply = dispatch_action("todo_reassign",
                            f"{instance.uuid}|{partner.pk}", "U0NITIN")

    instance.task.refresh_from_db()
    assert instance.task.owner == partner
    assert partner.name in reply


def test_a_button_for_a_vanished_task_fails_gracefully(slack_member):
    import uuid as uuid_module

    reply = dispatch_action("todo_done", str(uuid_module.uuid4()), "U0NITIN")

    assert "no longer there" in reply


def test_a_malformed_button_value_does_not_raise(slack_member):
    """Django raises ValidationError on a non-uuid uuid lookup, inside a socket
    thread where nothing would catch it."""
    assert "no longer there" in dispatch_action("todo_done", "not-a-uuid", "U0NITIN")


def test_a_button_cannot_complete_someone_elses_task(make_member, slack_member):
    stranger = make_member("kid")
    task = Task.objects.create(title="Not yours", owner=stranger, priority=Priority.P2)
    instance = Instance.objects.create(task=task, due_at=timezone.now())

    reply = dispatch_action("todo_done", str(instance.uuid), "U0NITIN")

    instance.refresh_from_db()
    assert instance.outcome == InstanceOutcome.PENDING
    assert "neither the owner nor an assignee" in reply


# ── the socket's own decisions ───────────────────────────────────────────────

def test_a_slash_command_payload_is_routed_and_left_standing(slack_member):
    text, replace = slack_socket.reply_for("slash_commands", {
        "command": "/todo", "text": "list", "user_id": "U0NITIN",
    })

    assert "Nothing open" in text
    assert replace is False   # an ephemeral reply has no message of ours to replace


def test_a_button_payload_replaces_the_message_it_came_from(slack_member, due_instance):
    instance = due_instance()

    text, replace = slack_socket.reply_for("interactive", {
        "user": {"id": "U0NITIN"},
        "actions": [{"action_id": "todo_done", "value": str(instance.uuid)}],
    })

    assert "done" in text.lower()
    # An answered reminder must stop looking like a question, or someone taps
    # a button that no longer applies.
    assert replace is True


def test_a_select_payload_reads_the_chosen_option(make_member, slack_member,
                                                  due_instance):
    partner = make_member("partner", role="adult")
    instance = due_instance()

    text, _ = slack_socket.reply_for("interactive", {
        "user": {"id": "U0NITIN"},
        "actions": [{"action_id": "todo_reassign",
                     "selected_option": {"value": f"{instance.uuid}|{partner.pk}"}}],
    })

    instance.task.refresh_from_db()
    assert instance.task.owner == partner
    assert partner.name in text


def test_an_unrecognised_payload_type_is_ignored_quietly(db):
    assert slack_socket.reply_for("event_callback", {}) == ("", False)


def test_socket_mode_reports_itself_unconfigured_without_both_tokens(settings):
    settings.NORA_HOME_SLACK_APP_TOKEN = ""
    settings.NORA_HOME_SLACK_BOT_TOKEN = "xoxb-something"

    assert slack_socket.is_configured() is False


def test_building_a_client_without_tokens_explains_the_fix(settings):
    settings.NORA_HOME_SLACK_APP_TOKEN = ""
    settings.NORA_HOME_SLACK_BOT_TOKEN = ""

    with pytest.raises(slack_socket.SlackSocketNotConfigured) as caught:
        slack_socket.build_client()

    assert "connections:write" in str(caught.value)


# ── the Block Kit those buttons come from ────────────────────────────────────

def _blocks_for(**context):
    notification = Notification.objects.create(
        app_slug="todo", title="Due: Take the bins out", body="Due today.",
        severity="info", context=context)
    return SlackChannel()._blocks(notification)


def _action_elements(blocks):
    for block in blocks:
        if block["type"] == "actions":
            return block["elements"]
    return []


def test_a_notification_with_no_actions_renders_none(db):
    assert _action_elements(_blocks_for()) == []


def test_slack_actions_become_buttons(db):
    elements = _action_elements(_blocks_for(slack_actions=[
        {"action_id": "todo_done", "text": "Done", "value": "abc", "style": "primary"},
    ]))

    assert elements[0]["type"] == "button"
    assert elements[0]["action_id"] == "todo_done"
    assert elements[0]["style"] == "primary"


def test_an_invalid_style_is_dropped_rather_than_sent(db):
    """Slack rejects the whole message for style:"default" — the absence of the
    key is what means default."""
    elements = _action_elements(_blocks_for(slack_actions=[
        {"action_id": "todo_skip", "text": "Skip", "value": "abc", "style": "default"},
    ]))

    assert "style" not in elements[0]


def test_options_become_a_select_not_a_button(db):
    elements = _action_elements(_blocks_for(slack_actions=[
        {"action_id": "todo_reassign", "text": "Reassign",
         "options": [{"text": "Partner", "value": "abc|2"}]},
    ]))

    assert elements[0]["type"] == "static_select"
    assert elements[0]["options"][0]["value"] == "abc|2"


def test_a_malformed_action_costs_only_its_own_button(db):
    elements = _action_elements(_blocks_for(slack_actions=[
        "not a dict", {"text": "no action_id"},
        {"action_id": "todo_done", "text": "Done", "value": "abc"},
    ]))

    assert len(elements) == 1
    assert elements[0]["action_id"] == "todo_done"


def test_a_reminder_carries_its_buttons(slack_member, due_instance):
    """End to end through the real reminder path — the action_ids here are the
    contract between reminders.py and slack_commands.py, and a rename on either
    side breaks the buttons silently."""
    from nora_home.todo.reminders import send_due_reminders

    instance = due_instance()
    Reminder.objects.filter(task=instance.task).delete()
    Reminder.objects.create(task=instance.task, offset_minutes=0)

    send_due_reminders()

    notification = Notification.objects.filter(recipient=slack_member).first()
    assert notification is not None
    ids = {a["action_id"] for a in notification.context["slack_actions"]}
    assert {"todo_done", "todo_snooze"} <= ids
    # Every button offered must have a handler registered for it, or it is a
    # control that does nothing on someone's phone.
    assert set(ids) <= set(registered_actions())


def test_a_reminder_at_the_due_moment_offers_no_skip(slack_member, due_instance):
    """The default reminder fires exactly at `due_at`, by which point §5 has
    already turned the occasion into a miss — so Skip would be present and
    permanently broken. Rendering it only when it can work is the same rule
    §10 applies to empty charts: do not draw a control that cannot act."""
    from nora_home.todo.reminders import send_due_reminders

    instance = due_instance()
    Reminder.objects.filter(task=instance.task).delete()
    Reminder.objects.create(task=instance.task, offset_minutes=0)

    send_due_reminders()

    notification = Notification.objects.filter(recipient=slack_member).first()
    ids = {a["action_id"] for a in notification.context["slack_actions"]}
    assert "todo_skip" not in ids


def test_a_reminder_sent_early_does_offer_skip(slack_member, make_task):
    """The other half: a reminder set 30 minutes ahead arrives while declining
    is still a decision, and there Skip is exactly the right control."""
    from nora_home.todo.reminders import send_due_reminders

    task = make_task()
    instance = Instance.objects.create(
        task=task, due_at=timezone.now() + timedelta(minutes=20))
    Reminder.objects.filter(task=task).delete()
    Reminder.objects.create(task=task, offset_minutes=30)  # fires 30m before

    send_due_reminders()

    notification = Notification.objects.filter(recipient=slack_member).first()
    ids = {a["action_id"] for a in notification.context["slack_actions"]}
    assert "todo_skip" in ids
