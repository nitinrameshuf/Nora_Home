"""
The board and its actions, requested for real through the test client — the
same reasoning as test_pages.py: a renamed URL name in a template or a
context key a view stopped setting is invisible to nora_home.todo.api's own
tests, and only shows up when a page is actually rendered.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from nora_home.todo.models import Label, Priority, Task, TaskState
from nora_home.todo.scheduling import current_instance, materialize

pytestmark = pytest.mark.django_db

MONDAY = timezone.localdate() + timedelta(days=1)


@pytest.fixture
def task(member):
    t = Task.objects.create(title="Water the plants", owner=member,
                            priority=Priority.P2, due_on=MONDAY)
    materialize(t)
    return t


def test_the_board_groups_tasks_by_priority(client, member, task):
    client.force_login(member)

    response = client.get(reverse("todo:board"))

    assert response.status_code == 200
    assert task.title.encode() in response.content


def test_the_board_only_shows_the_signed_in_members_tasks(client, member, make_member, task):
    stranger = make_member("stranger")
    client.force_login(stranger)

    response = client.get(reverse("todo:board"))

    assert task.title.encode() not in response.content


def test_creating_a_task_through_the_form(client, member):
    client.force_login(member)

    response = client.post(reverse("todo:create"), {
        "title": "Renew the passport", "description": "", "priority": Priority.P1,
        "owner": member.pk, "assignees": [], "labels": [], "due_on": MONDAY.isoformat(),
        "recurrence_type": "none", "recurrence_kind": "daily",
    })

    assert response.status_code == 302
    task = Task.objects.get(title="Renew the passport")
    assert task.owner == member
    assert task.instances.count() == 1


def test_creating_a_recurring_task_with_an_approver_is_refused_on_the_form(
        client, member, make_member):
    client.force_login(member)
    approver = make_member("approver")

    response = client.post(reverse("todo:create"), {
        "title": "Daily standup", "description": "", "priority": Priority.P2,
        "owner": member.pk, "assignees": [], "labels": [], "approver": approver.pk,
        "recurrence_type": "fixed", "recurrence_kind": "daily",
    })

    assert response.status_code == 200  # re-rendered with an error, not saved
    assert not Task.objects.filter(title="Daily standup").exists()


def test_completing_a_task_through_the_view(client, member, task):
    client.force_login(member)
    instance = current_instance(task)

    response = client.post(reverse("todo:complete", args=[instance.uuid]))

    assert response.status_code == 302
    instance.refresh_from_db()
    assert instance.outcome == "done"
    task.refresh_from_db()
    assert task.state == TaskState.DONE  # one-shot, so it leaves the board


def test_completing_someone_elses_task_is_refused(client, task, make_member):
    stranger = make_member("stranger")
    client.force_login(stranger)
    instance = current_instance(task)

    response = client.post(reverse("todo:complete", args=[instance.uuid]))

    assert response.status_code == 302  # redirected with an error message
    instance.refresh_from_db()
    assert instance.outcome == "pending"


def test_completing_via_fetch_gets_json_not_a_redirect(client, member, task):
    client.force_login(member)
    instance = current_instance(task)

    response = client.post(reverse("todo:complete", args=[instance.uuid]),
                           HTTP_X_REQUESTED_WITH="fetch")

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_a_denied_action_over_fetch_is_a_json_error_not_a_redirect(
        client, task, make_member):
    stranger = make_member("stranger")
    client.force_login(stranger)
    instance = current_instance(task)

    response = client.post(reverse("todo:complete", args=[instance.uuid]),
                           HTTP_X_REQUESTED_WITH="fetch")

    assert response.status_code == 403
    assert response.json()["ok"] is False


def test_archiving_and_restoring_a_task(client, member, task):
    client.force_login(member)

    client.post(reverse("todo:archive", args=[task.uuid]))
    task.refresh_from_db()
    assert task.state == TaskState.ARCHIVED
    assert task.priority == Priority.P2  # kept, so restoring puts it back

    client.post(reverse("todo:restore", args=[task.uuid]))
    task.refresh_from_db()
    assert task.state == TaskState.OPEN


def test_anyone_can_delete_anyones_task(client, task, make_member):
    """§4: "Anyone can create a task for anyone. No approval, no declining.
    If someone doesn't want it, they delete it." — no ownership gate here."""
    stranger = make_member("stranger")
    client.force_login(stranger)

    client.post(reverse("todo:delete", args=[task.uuid]))

    task.refresh_from_db()
    assert task.deleted_at is not None


def test_a_shared_tasks_approve_and_reject_flow_end_to_end(client, member, make_member):
    approver = make_member("approver")
    task = Task.objects.create(title="Fix the fence", owner=member, priority=Priority.P1,
                               due_on=MONDAY, approver=approver)
    materialize(task)
    client.force_login(member)
    instance = current_instance(task)

    client.post(reverse("todo:complete", args=[instance.uuid]))
    instance.refresh_from_db()
    assert instance.outcome == "awaiting_approval"

    client.force_login(approver)
    response = client.post(reverse("todo:reject", args=[instance.uuid]),
                           {"reason": "Still wobbly"})
    assert response.status_code == 302
    instance.refresh_from_db()
    assert instance.outcome == "pending"

    client.force_login(member)
    client.post(reverse("todo:complete", args=[instance.uuid]))
    client.force_login(approver)
    client.post(reverse("todo:approve", args=[instance.uuid]))
    instance.refresh_from_db()
    assert instance.outcome == "done"
    task.refresh_from_db()
    assert task.state == TaskState.DONE


def test_rejecting_with_no_reason_is_refused_by_the_view(client, member, make_member):
    approver = make_member("approver")
    task = Task.objects.create(title="Fix the fence", owner=member, priority=Priority.P1,
                               due_on=MONDAY, approver=approver)
    materialize(task)
    client.force_login(member)
    instance = current_instance(task)
    client.post(reverse("todo:complete", args=[instance.uuid]))

    client.force_login(approver)
    client.post(reverse("todo:reject", args=[instance.uuid]), {"reason": ""})

    instance.refresh_from_db()
    assert instance.outcome == "awaiting_approval"


def test_the_board_filters_by_label(client, member, task):
    home = Label.objects.create(name="Home")
    task.labels.add(home)
    other = Task.objects.create(title="Read a book", owner=member, priority=Priority.P3,
                                due_on=MONDAY)
    materialize(other)
    client.force_login(member)

    response = client.get(reverse("todo:board"), {"label": "Home"})

    assert task.title.encode() in response.content
    assert other.title.encode() not in response.content


def test_due_today_filters_to_only_todays_instances(client, member, task):
    """The kiosk's "Due today" tile lands on this same board, filtered —
    §6.3/6.4."""
    tomorrow = Task.objects.create(title="Due tomorrow", owner=member, priority=Priority.P3,
                                   due_on=MONDAY + timedelta(days=1))
    materialize(tomorrow)
    client.force_login(member)

    response = client.get(reverse("todo:board"), {"due": "today"})

    assert task.title.encode() not in response.content
    assert tomorrow.title.encode() not in response.content


def test_due_today_shows_a_task_actually_due_today(client, member):
    today_task = Task.objects.create(title="Due right now", owner=member, priority=Priority.P2,
                                     due_on=timezone.localdate())
    materialize(today_task)
    client.force_login(member)

    response = client.get(reverse("todo:board"), {"due": "today"})

    assert today_task.title.encode() in response.content


# ── Archived is a filter, not a fourth column (Story 53) ─────────────────────

def test_archived_task_is_off_the_board_by_default(client, member, task):
    client.force_login(member)
    client.post(reverse("todo:archive", args=[task.uuid]))

    response = client.get(reverse("todo:board"))

    assert task.title.encode() not in response.content


def test_the_archived_chip_shows_only_archived_tasks(client, member, task):
    other = Task.objects.create(title="Still open", owner=member, priority=Priority.P2,
                                due_on=MONDAY)
    materialize(other)
    client.force_login(member)
    client.post(reverse("todo:archive", args=[task.uuid]))

    response = client.get(reverse("todo:board"), {"archived": "1"})

    assert task.title.encode() in response.content
    assert other.title.encode() not in response.content


def test_the_board_has_no_fourth_archived_column(client, member, task):
    """The dashboard's own Story 53 notes: a row of P1/P2/P3 plus Archived
    made a state look like a level of urgency. There is no fourth .col-h
    labelled Archived any more — it is a chip in the toolbar instead."""
    client.force_login(member)

    response = client.get(reverse("todo:board"))

    assert b"<b>Archived</b>" not in response.content  # the old column heading
    assert b"?archived=1" in response.content  # the chip is still reachable


# ── the task Sheet (Story 53) ─────────────────────────────────────────────────

def test_the_board_offers_add_task_per_column_not_a_toolbar_button(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:board"))

    assert b"New task" not in response.content
    assert response.content.count(b"data-sheet-open") == 3  # one per priority column
    assert b"?priority=1" in response.content
    assert b"?priority=2" in response.content
    assert b"?priority=3" in response.content


def test_create_over_fetch_returns_the_sheet_fragment_not_a_full_page(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:create"), HTTP_X_REQUESTED_WITH="fetch")

    assert response.status_code == 200
    assert b"data-nh-sheet" in response.content
    assert b'<html' not in response.content  # a fragment, not the whole shell


def test_create_over_fetch_prefills_the_column_priority(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:create"), {"priority": "1"},
                          HTTP_X_REQUESTED_WITH="fetch")

    assert b'value="1" required id="id_priority_0" checked' in response.content


def test_a_nonsense_priority_query_param_is_ignored_not_500ed(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:create"), {"priority": "not-a-priority"},
                          HTTP_X_REQUESTED_WITH="fetch")

    assert response.status_code == 200


def test_creating_a_task_over_fetch_returns_json_not_a_redirect(client, member):
    client.force_login(member)

    response = client.post(reverse("todo:create"), {
        "title": "Renew the passport", "description": "", "priority": Priority.P1,
        "owner": member.pk, "assignees": [], "labels": [], "due_on": MONDAY.isoformat(),
        "recurrence_type": "none", "recurrence_kind": "daily",
    }, HTTP_X_REQUESTED_WITH="fetch")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["redirect"] == reverse("todo:board")
    assert Task.objects.filter(title="Renew the passport").exists()


def test_an_invalid_task_over_fetch_re_renders_the_sheet_with_a_422(client, member, make_member):
    """The sheet has to show the error inline rather than navigate away — a
    plain redirect would lose the half-filled form."""
    client.force_login(member)
    approver = make_member("approver")

    response = client.post(reverse("todo:create"), {
        "title": "Daily standup", "description": "", "priority": Priority.P2,
        "owner": member.pk, "assignees": [], "labels": [], "approver": approver.pk,
        "recurrence_type": "fixed", "recurrence_kind": "daily",
    }, HTTP_X_REQUESTED_WITH="fetch")

    assert response.status_code == 422
    assert b"data-nh-sheet" in response.content
    assert not Task.objects.filter(title="Daily standup").exists()


def test_editing_over_fetch_returns_json_with_the_detail_redirect(client, member, task):
    client.force_login(member)

    response = client.post(reverse("todo:edit", args=[task.uuid]), {
        "title": task.title, "description": "", "priority": Priority.P1,
        "owner": member.pk, "assignees": [], "labels": [], "due_on": MONDAY.isoformat(),
        "recurrence_type": "none", "recurrence_kind": "daily",
    }, HTTP_X_REQUESTED_WITH="fetch")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["redirect"] == reverse("todo:detail", args=[task.uuid])


def test_the_system_board_offers_no_add_task_button(client, member):
    """§8: system tasks are created by the platform, never by hand."""
    client.force_login(member)

    response = client.get(reverse("todo:system_board"))

    assert b"data-sheet-open" not in response.content


# ── quick-date chips (Story 53) ────────────────────────────────────────────────

def test_the_detail_pages_due_date_does_not_leak_a_raw_format_string(client, member, task):
    """Found live in the browser while checking Story 53: `&middot;` written
    *inside* a `date` filter's format string is read as format characters
    (m/i/d/o/t are all real ones), not a literal separator — it rendered as
    something like "&08001010202631;" instead of a middot. The two `date`
    calls in _card.html already do this safely; detail.html's Current card
    was the one place still putting it inside the string."""
    client.force_login(member)

    response = client.get(reverse("todo:detail", args=[task.uuid]))

    assert b"&middot;" in response.content
    assert b"08001010202631" not in response.content


def test_the_sheet_carries_the_quick_date_chips(client, member):
    client.force_login(member)

    response = client.get(reverse("todo:create"), HTTP_X_REQUESTED_WITH="fetch")

    for label in [b"Today", b"Tomorrow", b"This weekend", b"Next week", b"No date"]:
        assert label in response.content
    assert response.content.count(b"data-quick-date") == 5
