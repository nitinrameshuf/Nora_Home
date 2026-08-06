"""
Search's filtering (docs/Main_App/subsystems/todo.md §7) and the labels page
(§6). `nora_home.todo.search` is tested standalone against a plain queryset,
then the view is tested through the real request cycle for the parts a unit
test can't see — an empty page on first load, a saved filter round-tripping
through a real POST and a real redirect.
"""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from nora_home.todo.models import Comment, Label, Priority, SavedFilter, Task, TaskState
from nora_home.todo.scheduling import materialize
from nora_home.todo.search import FilterParams, search_tasks

pytestmark = pytest.mark.django_db


@pytest.fixture
def make_task(member):
    def _make(**kwargs):
        kwargs.setdefault("title", "A thing")
        kwargs.setdefault("owner", member)
        kwargs.setdefault("priority", Priority.P2)
        return Task.objects.create(**kwargs)

    return _make


# ── FilterParams ─────────────────────────────────────────────────────────────

def test_params_from_an_empty_dict_is_empty():
    assert FilterParams.from_dict({}).is_empty()


def test_params_with_any_field_set_is_not_empty():
    assert not FilterParams.from_dict({"q": "plants"}).is_empty()


def test_overdue_is_parsed_from_a_querystring_style_string():
    assert FilterParams.from_dict({"overdue": "1"}).overdue is True
    assert FilterParams.from_dict({"overdue": "on"}).overdue is True
    assert FilterParams.from_dict({}).overdue is False


def test_an_unknown_field_is_silently_ignored():
    """A stray param, a typo, an old saved filter from a removed field — none
    of it should stop the page from loading."""
    params = FilterParams.from_dict({"q": "plants", "nonsense": "whatever"})

    assert params.q == "plants"


def test_as_dict_omits_empty_fields():
    params = FilterParams(q="plants")

    assert params.as_dict() == {"q": "plants"}


# ── search_tasks ─────────────────────────────────────────────────────────────

def test_text_matches_the_title(make_task):
    match = make_task(title="Water the plants")
    make_task(title="Read a book")

    results = search_tasks(Task.objects.all(), FilterParams(q="plants"))

    assert list(results) == [match]


def test_text_matches_the_description(make_task):
    match = make_task(title="Chore", description="Refill the bird feeder")

    results = search_tasks(Task.objects.all(), FilterParams(q="bird feeder"))

    assert list(results) == [match]


def test_text_matches_a_task_level_comment(make_task, member):
    task = make_task(title="Fix the fence")
    Comment.objects.create(task=task, author=member, body="Needs a new post")

    results = search_tasks(Task.objects.all(), FilterParams(q="new post"))

    assert list(results) == [task]


def test_text_matches_an_instance_level_comment(make_task, member):
    task = make_task(title="Water the succulent", due_on=timezone.localdate())
    materialize(task)
    instance = task.instances.get()
    Comment.objects.create(instance=instance, author=member, body="Looked droopy today")

    results = search_tasks(Task.objects.all(), FilterParams(q="droopy"))

    assert list(results) == [task]


def test_a_task_matching_by_both_title_and_comment_appears_once(make_task, member):
    """The comment join can duplicate rows — this is exactly what .distinct()
    in search_tasks() exists to prevent."""
    task = make_task(title="Plants need water")
    Comment.objects.create(task=task, author=member, body="Water the plants please")

    results = search_tasks(Task.objects.all(), FilterParams(q="water"))

    assert list(results) == [task]


def test_filters_combine(make_task):
    make_task(title="A", priority=Priority.P1)
    match = make_task(title="B", priority=Priority.P1, state=TaskState.ARCHIVED)
    make_task(title="C", priority=Priority.P2, state=TaskState.ARCHIVED)

    results = search_tasks(Task.objects.all(),
                           FilterParams(priority=str(Priority.P1), state=TaskState.ARCHIVED))

    assert list(results) == [match]


def test_label_filters_correctly(make_task):
    home = Label.objects.create(name="Home")
    match = make_task(title="A")
    match.labels.add(home)
    make_task(title="B")

    results = search_tasks(Task.objects.all(), FilterParams(label="Home"))

    assert list(results) == [match]


def test_owner_filters_correctly(make_task, make_member):
    bob = make_member("bob")
    match = make_task(title="A", owner=bob)
    make_task(title="B")

    results = search_tasks(Task.objects.all(), FilterParams(owner_id=str(bob.pk)))

    assert list(results) == [match]


def test_due_range_filters_correctly(make_task):
    today = timezone.localdate()
    in_range = make_task(title="A", due_on=today)
    make_task(title="B", due_on=today + timedelta(days=30))

    results = search_tasks(Task.objects.all(),
                           FilterParams(due_after=str(today), due_before=str(today + timedelta(days=5))))

    assert list(results) == [in_range]


def test_overdue_only_matches_a_pending_instance_past_its_due_moment(make_task, member):
    from nora_home.todo import api

    overdue_task = make_task(title="Overdue", due_on=timezone.localdate() - timedelta(days=2))
    materialize(overdue_task)
    overdue_task.instances.update(due_at=timezone.now() - timedelta(days=2))

    not_overdue = make_task(title="Not due yet", due_on=timezone.localdate() + timedelta(days=2))
    materialize(not_overdue)

    done_task = make_task(title="Already done", due_on=timezone.localdate() - timedelta(days=2))
    materialize(done_task)
    done_task.instances.update(due_at=timezone.now() - timedelta(days=2))
    api.complete(done_task.instances.get(), member=member)

    results = search_tasks(Task.objects.all(), FilterParams(overdue=True))

    assert list(results) == [overdue_task]


# ── the search page ──────────────────────────────────────────────────────────

def test_the_search_page_shows_nothing_on_first_load(client, member, make_task):
    make_task(title="Water the plants")
    client.force_login(member)

    response = client.get(reverse("todo:search"))

    assert b"Water the plants" not in response.content
    assert b"Search or apply a filter" in response.content


def test_the_search_page_shows_results_once_filtered(client, member, make_task):
    make_task(title="Water the plants")
    client.force_login(member)

    response = client.get(reverse("todo:search"), {"q": "plants"})

    assert b"Water the plants" in response.content


def test_search_only_returns_tasks_the_signed_in_member_can_see(
        client, member, make_member, make_task):
    stranger = make_member("stranger")
    make_task(title="Someone elses task", owner=stranger)
    client.force_login(member)

    response = client.get(reverse("todo:search"), {"q": "task"})

    assert b"Someone elses task" not in response.content


def test_saving_a_search_round_trips_through_a_real_post(client, member):
    client.force_login(member)

    response = client.post(reverse("todo:save_filter"), {"name": "My overdue", "overdue": "1"})

    assert response.status_code == 302
    saved = SavedFilter.objects.get(owner=member, name="My overdue")
    assert saved.params == {"overdue": True}
    assert "overdue=True" in response.url


def test_saving_a_search_with_no_name_is_refused(client, member):
    client.force_login(member)

    client.post(reverse("todo:save_filter"), {"overdue": "1"})

    assert not SavedFilter.objects.exists()


def test_saving_a_search_with_no_filters_is_refused(client, member):
    client.force_login(member)

    client.post(reverse("todo:save_filter"), {"name": "Empty"})

    assert not SavedFilter.objects.exists()


def test_saving_the_same_name_twice_updates_rather_than_duplicates(client, member):
    client.force_login(member)
    client.post(reverse("todo:save_filter"), {"name": "Mine", "priority": "1"})

    client.post(reverse("todo:save_filter"), {"name": "Mine", "priority": "2"})

    assert SavedFilter.objects.filter(owner=member, name="Mine").count() == 1
    assert SavedFilter.objects.get(owner=member, name="Mine").params["priority"] == "2"


def test_deleting_a_saved_filter(client, member):
    saved = SavedFilter.objects.create(owner=member, name="Mine", params={"priority": "1"})
    client.force_login(member)

    client.post(reverse("todo:delete_saved_filter", args=[saved.pk]))

    assert not SavedFilter.objects.filter(pk=saved.pk).exists()


def test_a_member_cannot_delete_someone_elses_saved_filter(client, member, make_member):
    stranger = make_member("stranger")
    saved = SavedFilter.objects.create(owner=stranger, name="Theirs", params={"priority": "1"})
    client.force_login(member)

    client.post(reverse("todo:delete_saved_filter", args=[saved.pk]))

    assert SavedFilter.objects.filter(pk=saved.pk).exists()


# ── labels ───────────────────────────────────────────────────────────────────

def test_the_labels_page_shows_a_live_count(client, member, make_task):
    home = Label.objects.create(name="Home")
    for _ in range(3):
        make_task().labels.add(home)
    client.force_login(member)

    response = client.get(reverse("todo:labels"))

    assert b">3<" in response.content


def test_an_archived_tasks_label_does_not_count(client, member, make_task):
    home = Label.objects.create(name="Home")
    task = make_task(state=TaskState.ARCHIVED)
    task.labels.add(home)
    client.force_login(member)

    response = client.get(reverse("todo:labels"))

    assert b">0<" in response.content


def test_creating_a_label_from_the_page(client, member):
    client.force_login(member)

    client.post(reverse("todo:labels"), {"name": "Ambition", "colour": "#7dd3fc"})

    assert Label.objects.filter(name="Ambition", colour="#7dd3fc").exists()


def test_creating_a_label_that_already_exists_does_not_duplicate(client, member):
    Label.objects.create(name="Home")
    client.force_login(member)

    client.post(reverse("todo:labels"), {"name": "Home"})

    assert Label.objects.filter(name="Home").count() == 1


# ── kiosk ────────────────────────────────────────────────────────────────────

def test_todo_declares_kiosk_controls_that_all_resolve():
    """§6.3: kiosk controls are title/path pairs the kiosk can navigate the
    wall to. Every declared path must be a real, reachable URL — a kiosk
    button pointing at a 404 on a wall-mounted touchscreen is worse than one
    that doesn't exist (see apps.py for why Reporting/System tasks aren't
    listed yet)."""
    from django.test import Client
    from django.urls import resolve

    from nora_home.core.registry import registered_apps

    todo = next(a for a in registered_apps() if a.slug == "todo")
    assert todo.kiosk_controls, "Todo declared no kiosk controls at all"

    for control in todo.kiosk_controls:
        assert "title" in control and "path" in control
        resolve(control["path"].split("?")[0])  # raises Resolver404 if unreachable
