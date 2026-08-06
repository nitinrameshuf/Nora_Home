"""
The registry a slash command or a message button dispatches through.

**This module is deliberately ignorant of what any command means.** It knows
how to turn a Slack user id into a `HouseMember`, how to find the handler an
incoming payload asked for, and how to fail safely — nothing else. Todo
registers `/todo` from `nora_home.todo.slack_commands`, the same way
integrations register themselves in `IntegrationsConfig.ready()`, so the base
platform never imports the app (CLAUDE.md §6, and §4's Levels rule).

Handlers take `(member, text)` and return a plain string, which becomes the
reply Slack shows. They may raise: `dispatch_*` turns any exception into an
apology and a log line, because an unhandled error here would otherwise be a
button that silently does nothing on someone's phone.
"""

from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

_COMMANDS: dict[str, Callable] = {}
_ACTIONS: dict[str, Callable] = {}

# What an unrecognised Slack account is told. Deliberately specific: the fix is
# always the same one field, and "who are you" is a bad thing for a house
# system to say without saying what to do about it.
UNKNOWN_MEMBER = (
    "I don't know which house member you are. Someone with admin access can set "
    "your Slack ID in /admin/ (HouseMember -> slack_user_id), or run "
    "`manage.py slack_members` to list them."
)


def command(name: str):
    """Register a handler for a slash command, e.g. `@command("/todo")`."""
    def register(func):
        _COMMANDS[name] = func
        return func
    return register


def action(action_id: str):
    """Register a handler for a Block Kit element's `action_id`."""
    def register(func):
        _ACTIONS[action_id] = func
        return func
    return register


def registered_commands() -> list[str]:
    return sorted(_COMMANDS)


def registered_actions() -> list[str]:
    return sorted(_ACTIONS)


def member_for(slack_user_id: str):
    """The house member behind a Slack account, or None.

    Matching is on `slack_user_id` alone — never on name or email. A Slack
    display name is not an identity, and acting on a guess here would mean
    completing somebody else's task.
    """
    from nora_home.accounts.models import HouseMember

    if not slack_user_id:
        return None
    return HouseMember.objects.filter(slack_user_id=slack_user_id,
                                      is_active=True).first()


def dispatch_command(name: str, text: str, slack_user_id: str) -> str:
    handler = _COMMANDS.get(name)
    if handler is None:
        logger.warning("No handler registered for Slack command %r", name)
        return f"`{name}` isn't a command this house knows."

    member = member_for(slack_user_id)
    if member is None:
        return UNKNOWN_MEMBER

    try:
        return handler(member, (text or "").strip())
    except Exception:
        logger.exception("Slack command %s failed for %s", name, member)
        return "Something went wrong handling that. It's been logged."


def dispatch_action(action_id: str, value: str, slack_user_id: str) -> str:
    handler = _ACTIONS.get(action_id)
    if handler is None:
        logger.warning("No handler registered for Slack action %r", action_id)
        return "That button no longer does anything."

    member = member_for(slack_user_id)
    if member is None:
        return UNKNOWN_MEMBER

    try:
        return handler(member, (value or "").strip())
    except Exception:
        logger.exception("Slack action %s failed for %s", action_id, member)
        return "Something went wrong handling that. It's been logged."
