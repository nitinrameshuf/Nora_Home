"""
Celery wiring.

Broker is RabbitMQ, results land in the relational DB via django-celery-results, and
the beat schedule is stored in the database so a family member can retime a job from
the admin without a deploy.

House apps do not need to touch this file: any `tasks.py` inside an installed app is
autodiscovered. Route your task to a queue with
`@shared_task(queue="apps")` (the default) or `queue="ai"` for model calls.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab
from celery.signals import setup_logging

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

app = Celery("nora_home")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()


@setup_logging.connect
def configure_logging(**_kwargs):
    """Use Django's LOGGING dict rather than Celery's own format."""
    from logging.config import dictConfig

    from django.conf import settings

    dictConfig(settings.LOGGING)


# Platform heartbeat schedule. Anything a house app needs on a schedule should be
# registered as a PeriodicTask row instead (see docs/Main_App/DEVELOPMENT.md), not added here.
app.conf.beat_schedule = {
    "tracker.sweep-due": {
        "task": "nora_home.tracker.tasks.sweep_due_items",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "platform"},
    },
    "tracker.run-escalations": {
        "task": "nora_home.tracker.tasks.run_escalations",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "alerts"},
    },
    "tracker.materialize-schedules": {
        "task": "nora_home.tracker.tasks.materialize_schedules",
        "schedule": crontab(minute=5, hour="*"),
        "options": {"queue": "platform"},
    },
    "core.health-check": {
        "task": "nora_home.core.tasks.record_health_snapshot",
        "schedule": crontab(minute="*/10"),
        "options": {"queue": "platform"},
    },
    # "displays.rotate" used to fire every 45s to advance the ambient wall's
    # panel rotation. The wall now mirrors a real page chosen from the kiosk
    # and ignores "next" entirely, so the task was waking the worker every 45
    # seconds, forever, to send a message nothing listened for. Removed with
    # the task itself.
    "integrations.poll": {
        "task": "nora_home.integrations.tasks.poll_due_integrations",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "integrations"},
    },
    "telemetry.rollup": {
        "task": "nora_home.telemetry.tasks.rollup_hourly",
        "schedule": crontab(minute=7),
        "options": {"queue": "platform"},
    },
    "datastores.nightly-backup": {
        "task": "nora_home.datastores.tasks.nightly_backup",
        "schedule": crontab(minute=30, hour=3),
        "options": {"queue": "platform"},
    },
    "notifications.retry-failed": {
        "task": "nora_home.notifications.tasks.retry_failed_deliveries",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "alerts"},
    },
}


@app.task(bind=True, queue="platform")
def debug_task(self):
    """`celery -A config call config.celery.debug_task` — proves the broker works."""
    return f"nora worker alive: {self.request!r}"
