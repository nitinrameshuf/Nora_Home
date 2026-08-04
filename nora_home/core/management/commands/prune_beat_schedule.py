"""
Delete scheduled tasks that no longer exist in the code.

Why this is needed: beat runs on django_celery_beat's DatabaseScheduler, which
syncs `app.conf.beat_schedule` *into* the database on startup but never removes
what has been taken out of it. So deleting a periodic task from
`config/celery.py` leaves its row behind, and beat keeps dispatching it forever.

That is not hypothetical. `displays.rotate` was removed from the code on
2026-08-03 when the ambient wall was replaced by the iframe wall. It kept firing
every 45 seconds for the next day — the worker logging
`Received unregistered task ... KeyError` each time — across several rebuilds,
because nothing had ever deleted the row. It was found on 2026-08-04 only
because someone read the beat log while checking something else.

Run automatically before beat starts (see docker/entrypoint.sh), so a task
removed in a commit is a task actually gone after the next deploy.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

# Celery registers a few of its own periodic tasks that are legitimately absent
# from our beat_schedule. Deleting these would be wrong.
CELERY_BUILTINS = {"celery.backend_cleanup"}


class Command(BaseCommand):
    help = "Remove periodic task rows whose task no longer exists in the code."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run", action="store_true",
            help="List what would be removed without deleting anything.")

    def handle(self, *args, **options):
        try:
            from django_celery_beat.models import PeriodicTask
        except ImportError:
            self.stdout.write("django_celery_beat is not installed; nothing to prune.")
            return

        from config.celery import app

        # Registered tasks are the real authority: a task can be dispatched by
        # something other than beat_schedule, and anything importable is fine.
        app.loader.import_default_modules()
        known = set(app.tasks.keys()) | CELERY_BUILTINS
        known |= {entry["task"] for entry in app.conf.beat_schedule.values()}

        orphans = [t for t in PeriodicTask.objects.all() if t.task not in known]

        if not orphans:
            self.stdout.write("Beat schedule is clean; no orphaned tasks.")
            return

        for task in orphans:
            self.stdout.write(self.style.WARNING(
                f"  orphaned: {task.name} -> {task.task}"))

        if options["dry_run"]:
            self.stdout.write(f"{len(orphans)} orphaned task(s); --dry-run, nothing deleted.")
            return

        PeriodicTask.objects.filter(pk__in=[t.pk for t in orphans]).delete()
        self.stdout.write(self.style.SUCCESS(
            f"Removed {len(orphans)} orphaned periodic task(s)."))
