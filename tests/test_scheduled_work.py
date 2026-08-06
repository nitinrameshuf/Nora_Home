"""
The house's clock: what beat is configured to fire, and whether it still exists.

This file exists because of a bug that ran unnoticed for a day and a half.
`displays.rotate` was deleted from `config/celery.py` on 2026-08-03, but beat
runs on django_celery_beat's DatabaseScheduler, which syncs `beat_schedule` into
the database and never removes what has been taken out of it. The row survived
every rebuild, beat kept dispatching it every 45 seconds, and the worker logged
`Received unregistered task ... KeyError` each time. Nothing failed loudly; the
house just did pointless work forever.

Two defences, both tested here: every configured entry must point at a task that
actually imports, and `prune_beat_schedule` must remove rows that do not.
"""

from __future__ import annotations

from importlib import import_module

import pytest
from django.core.management import call_command

from config.celery import app

pytestmark = pytest.mark.django_db

SCHEDULE = app.conf.beat_schedule


def test_there_is_a_schedule():
    assert SCHEDULE, "beat has nothing scheduled at all"


@pytest.mark.parametrize("name", sorted(SCHEDULE))
def test_every_scheduled_task_can_actually_be_imported(name):
    """A scheduled task whose module or function has been renamed is dispatched
    forever and never runs. Importing it is the cheapest possible proof."""
    dotted = SCHEDULE[name]["task"]
    module_path, _, function = dotted.rpartition(".")

    module = import_module(module_path)

    assert hasattr(module, function), (
        f"beat entry {name!r} points at {dotted}, which does not exist")


@pytest.mark.parametrize("name", sorted(SCHEDULE))
def test_every_scheduled_task_is_registered_with_celery(name):
    """Importable is not enough — it has to carry @shared_task, or the worker
    rejects the message it is sent."""
    app.loader.import_default_modules()

    assert SCHEDULE[name]["task"] in app.tasks, (
        f"beat entry {name!r} is not a registered Celery task; the worker would "
        "reject it with 'Received unregistered task'")


@pytest.mark.parametrize("name", sorted(SCHEDULE))
def test_every_scheduled_task_has_a_schedule_and_a_queue(name):
    entry = SCHEDULE[name]

    assert entry.get("schedule") is not None, f"{name} has no schedule"
    queue = entry.get("options", {}).get("queue")
    assert queue, f"{name} declares no queue, so it lands on the default one"


def test_scheduled_queues_are_ones_the_worker_consumes():
    """The worker is started with an explicit --queues list. A task routed
    anywhere else is queued and never consumed — it just accumulates."""
    consumed = {"platform", "alerts", "apps", "ai", "integrations"}

    for name, entry in SCHEDULE.items():
        queue = entry.get("options", {}).get("queue")
        assert queue in consumed, (
            f"{name} is routed to {queue!r}, which the worker does not consume "
            "(see docker/entrypoint.sh)")


def test_the_removed_wall_rotation_task_is_really_gone():
    """The specific regression. `rotate_wall_display` belonged to the ambient
    wall that the iframe wall replaced; the wall has no handler for what it
    sent, so it was waking the worker forever to do nothing."""
    import nora_home.displays.tasks as display_tasks

    assert not hasattr(display_tasks, "rotate_wall_display")
    assert "displays.rotate" not in SCHEDULE


# ── the pruner ───────────────────────────────────────────────────────────────

def test_prune_removes_a_task_that_no_longer_exists():
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    every_minute, _ = IntervalSchedule.objects.get_or_create(
        every=1, period=IntervalSchedule.MINUTES)
    PeriodicTask.objects.create(
        name="displays.rotate", task="nora_home.displays.tasks.rotate_wall_display",
        interval=every_minute)

    call_command("prune_beat_schedule")

    assert not PeriodicTask.objects.filter(name="displays.rotate").exists()


def test_prune_keeps_tasks_that_do_exist():
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    every_minute, _ = IntervalSchedule.objects.get_or_create(
        every=1, period=IntervalSchedule.MINUTES)
    PeriodicTask.objects.create(
        name="todo.close-passed", task="nora_home.todo.tasks.close_passed",
        interval=every_minute)

    call_command("prune_beat_schedule")

    assert PeriodicTask.objects.filter(name="todo.close-passed").exists()


def test_prune_keeps_celerys_own_builtin_tasks():
    """celery.backend_cleanup is registered by Celery itself and is legitimately
    absent from our beat_schedule. Deleting it would be the pruner causing the
    very problem it exists to fix."""
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    every_minute, _ = IntervalSchedule.objects.get_or_create(
        every=1, period=IntervalSchedule.MINUTES)
    PeriodicTask.objects.create(name="celery.backend_cleanup",
                                task="celery.backend_cleanup", interval=every_minute)

    call_command("prune_beat_schedule")

    assert PeriodicTask.objects.filter(name="celery.backend_cleanup").exists()


def test_prune_dry_run_deletes_nothing():
    from django_celery_beat.models import IntervalSchedule, PeriodicTask

    every_minute, _ = IntervalSchedule.objects.get_or_create(
        every=1, period=IntervalSchedule.MINUTES)
    PeriodicTask.objects.create(name="ghost", task="nora_home.nope.gone",
                                interval=every_minute)

    call_command("prune_beat_schedule", "--dry-run")

    assert PeriodicTask.objects.filter(name="ghost").exists()


def test_prune_is_safe_to_run_when_nothing_is_wrong():
    call_command("prune_beat_schedule")
