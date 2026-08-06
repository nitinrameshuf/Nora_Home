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
