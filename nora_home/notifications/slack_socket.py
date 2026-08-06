"""
Socket Mode — the house's inbound half of Slack.

**Why a websocket rather than webhooks.** Slash commands and button clicks
require Slack to *reach the server*. This house is a Pi behind home NAT with a
self-signed certificate; Slack cannot call it, and no OAuth scope changes that
(docs/Main_App/subsystems/todo.md §12). Socket Mode inverts it: the app opens an
outbound websocket *to* Slack and answers over the same connection. No public
endpoint, no port forwarding, no tunnel, no domain.

The cost is one long-lived process, which is why this runs as its own container
beside `web`, `worker` and `beat` rather than inside any of them — a websocket
that must stay open does not belong in a request/response server or in a Celery
worker that restarts every 200 tasks.

**Two things here are not optional and both are easy to get wrong:**

1. **Acknowledge within three seconds, before doing any work.** Slack retries
   an unacknowledged envelope, so a slow handler does not produce a late reply
   — it produces the same task completed twice. `_handle` acks first and
   answers afterwards over `response_url`.
2. **Close stale database connections per request.** slack_sdk dispatches into
   its own thread pool, and Django's connections are thread-local; without
   `close_old_connections()` those threads accumulate connections MySQL has
   long since dropped, and the first symptom is an interaction failing hours
   after the process looked healthy.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings
from django.db import close_old_connections

from nora_home.notifications.slack_commands import dispatch_action, dispatch_command

logger = logging.getLogger(__name__)

RESPONSE_TIMEOUT = 10


class SlackSocketNotConfigured(RuntimeError):
    """Raised rather than looping: a missing token is a setup mistake, and a
    process that retries forever hides it in a log nobody reads."""


def is_configured() -> bool:
    return bool(settings.NORA_HOME_SLACK_APP_TOKEN and settings.NORA_HOME_SLACK_BOT_TOKEN)


def build_client():
    """The slack_sdk client, imported lazily so the rest of the house — and the
    test suite — never needs slack_sdk present just to import this module."""
    if not is_configured():
        raise SlackSocketNotConfigured(
            "Socket Mode needs both NORA_HOME_SLACK_APP_TOKEN (xapp-…, scope "
            "connections:write, from the app's Basic Information page) and "
            "NORA_HOME_SLACK_BOT_TOKEN (xoxb-…). Set them in .env and recreate "
            "the container — a running container keeps the environment it "
            "started with.")

    from slack_sdk.socket_mode import SocketModeClient
    from slack_sdk.web import WebClient

    return SocketModeClient(
        app_token=settings.NORA_HOME_SLACK_APP_TOKEN,
        web_client=WebClient(token=settings.NORA_HOME_SLACK_BOT_TOKEN),
    )


def reply_for(payload_type: str, payload: dict) -> tuple[str, bool]:
    """`(text, replace_original)` for one incoming interaction.

    Split out from the socket plumbing on purpose: everything this house
    actually decides happens here, against a plain dict, so it is testable
    without a network, a token, or slack_sdk installed.
    """
    if payload_type == "slash_commands":
        text = dispatch_command(payload.get("command", ""),
                                payload.get("text", ""),
                                payload.get("user_id", ""))
        # A slash command's reply is ephemeral and stands alone; there is no
        # original message of ours to replace.
        return text, False

    if payload_type == "interactive":
        user = (payload.get("user") or {}).get("id", "")
        for element in payload.get("actions") or []:
            # A link button still sends an interaction, and Slack still wants
            # it acknowledged — but there is nothing to run and nothing to say.
            # Found by tapping the real "Open in Nora Home" button on a real
            # message, which answered "that button no longer does anything"
            # while cheerfully opening the page it was pointing at.
            if element.get("url"):
                logger.debug("Link button opened: %s", element.get("action_id", ""))
                return "", False

            action_id = element.get("action_id", "")
            # A button carries `value`; a select carries the chosen option's.
            value = element.get("value") or (
                (element.get("selected_option") or {}).get("value", ""))
            text = dispatch_action(action_id, value, user)
            # Replacing the message is the point: a reminder that has been
            # answered should stop looking like a question. Leaving it would
            # invite a second tap on a button that no longer applies.
            return text, True
        return "", False

    logger.debug("Ignoring Slack payload of type %r", payload_type)
    return "", False


def respond(response_url: str, text: str, *, replace_original: bool) -> None:
    """Answer over the interaction's own `response_url`.

    Not `chat.postMessage`: the response_url works for the exact conversation
    the interaction came from, including a DM the bot has never opened, and it
    is what makes an ephemeral reply ephemeral.
    """
    if not (response_url and text):
        return
    try:
        requests.post(response_url, json={
            "text": text,
            "replace_original": replace_original,
        }, timeout=RESPONSE_TIMEOUT)
    except requests.RequestException:
        # The work already happened; only the acknowledgement was lost. Log it
        # and move on rather than letting the socket thread die.
        logger.exception("Could not post the Slack reply back to %s", response_url)


def _handle(client, req):
    from slack_sdk.socket_mode.response import SocketModeResponse

    # Ack first — see the module docstring. Everything after this is on our own
    # time; anything before it risks Slack retrying the same interaction.
    try:
        client.send_socket_mode_response(SocketModeResponse(envelope_id=req.envelope_id))
    except Exception:
        logger.exception("Failed to acknowledge a Slack envelope")
        return

    close_old_connections()
    try:
        payload = req.payload or {}
        text, replace = reply_for(req.type, payload)
        respond(payload.get("response_url", ""), text, replace_original=replace)
    except Exception:
        logger.exception("Unhandled error processing a Slack %s payload", req.type)
    finally:
        close_old_connections()


def run_forever() -> None:
    """Connect and block. The container's restart policy is the retry strategy —
    slack_sdk reconnects on its own for transient drops, and anything it cannot
    recover from should restart the process rather than be papered over here."""
    client = build_client()
    client.socket_mode_request_listeners.append(_handle)

    logger.info("Connecting to Slack over Socket Mode")
    client.connect()

    from threading import Event
    Event().wait()  # sleep forever; the listener threads do the work
