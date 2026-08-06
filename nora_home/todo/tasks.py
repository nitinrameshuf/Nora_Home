"""
Todo's scheduled work.

Four jobs, and between them they are what makes the board move on its own —
schedule, notice, remind, and chase.
"""

from __future__ import annotations

import logging

from celery import shared_task

from nora_home.todo.escalation import escalate_due_instances
from nora_home.todo.reminders import send_due_reminders
from nora_home.todo.scheduling import close_passed_instances, materialize_open_tasks

logger = logging.getLogger(__name__)


@shared_task(queue="platform")
def extend_windows():
    """Keep the 90-day horizon of fixed-recurrence instances filled in, and
    give rolling tasks their next occasion once the current one is done.

    Nightly is often enough: the horizon is 90 days, so even a month of missed
    runs would not exhaust it.
    """
    return materialize_open_tasks()


@shared_task(queue="platform")
def close_passed():
    """Mark instances whose turn has passed as missed.

    **This job is the only reason a missed day ever appears in any chart.**
    Without it every skipped occasion stays `pending` forever: the board shows
    a stale card from last week instead of today's, and Reporting counts a
    string of misses as if they were still open.
    """
    return close_passed_instances()


@shared_task(queue="platform")
def send_reminders():
    """Fire every reminder whose moment has arrived. See
    nora_home.todo.reminders — each (instance, reminder) pair fires once."""
    return send_due_reminders()


@shared_task(queue="alerts")
def run_escalations():
    """The heartbeat that makes an opted-in, unfinished task impossible to
    ignore. See nora_home.todo.escalation."""
    return escalate_due_instances()
