"""
Slack delivery.

Two modes, chosen automatically:
  * bot token (NORA_HOME_SLACK_BOT_TOKEN) — DMs individuals, threads, adds reactions;
  * incoming webhook (NORA_HOME_SLACK_WEBHOOK_URL) — one channel, no DMs, zero setup.

Escalations always go to NORA_HOME_SLACK_ESCALATION_CHANNEL so the whole house sees
them, in addition to the DM to the person responsible.
"""

from __future__ import annotations

import logging

import requests
from django.conf import settings

from nora_home.notifications.channels import BaseChannel, ChannelError

logger = logging.getLogger(__name__)

SLACK_API = "https://slack.com/api/chat.postMessage"
SLACK_CONVERSATIONS_OPEN = "https://slack.com/api/conversations.open"
TIMEOUT = 10

# Slack user IDs start with U (people) or W (Enterprise Grid people). Channel
# names start with #, and channel IDs with C/G — so this is enough to tell "DM a
# person" from "post in a room" without asking Slack which it is.
_USER_ID_PREFIXES = ("U", "W")

# Slack's error strings are accurate and useless — "channel_not_found" is what it
# says whether the channel does not exist, or exists and the bot was never invited
# to it. Since the fix is always a specific action in Slack's own UI, the message
# says which one. This cost a session on 2026-08-04: a valid token, a live
# workspace, and a bare "channel_not_found" with nothing pointing at the cause.
SLACK_ERROR_HELP = {
    "channel_not_found":
        "Slack cannot see {target}. Either the channel does not exist, or the bot "
        "was never invited to it — run `/invite @nora_home` in that channel, or "
        "grant the app the `chat:write.public` scope so it can post without "
        "joining.",
    "not_in_channel":
        "The bot is not a member of {target}. Run `/invite @nora_home` there.",
    "channel_is_archived":
        "{target} is archived. Point NORA_HOME_SLACK_DEFAULT_CHANNEL / "
        "_ESCALATION_CHANNEL at a live channel.",
    "missing_scope":
        "The bot token is missing a scope this call needs. DMs to a person need "
        "`im:write`; posting to a channel it has not joined needs "
        "`chat:write.public`; looking members up needs `users:read`. Add them in "
        "the Slack app config and reinstall the app.",
    "users_not_found":
        "Slack does not recognise {target} as a member of this workspace. Check "
        "the member's slack_user_id in /admin/ — `manage.py slack_members` lists "
        "the real ones.",
    "cannot_dm_bot":
        "{target} is a bot, not a person. Only people can be DMed.",
    "invalid_auth":
        "Slack rejected the token. Check NORA_HOME_SLACK_BOT_TOKEN in .env — it "
        "must start with `xoxb-` and carry no surrounding quotes.",
    "account_inactive":
        "The bot's Slack account is deactivated or the app was uninstalled.",
    "is_archived": "{target} is archived.",
}

SEVERITY_STYLE = {
    "info": (":information_source:", "#60a5fa"),
    "nudge": (":wave:", "#a78bfa"),
    "warning": (":warning:", "#fbbf24"),
    "alert": (":rotating_light:", "#fb7185"),
    "critical": (":rotating_light:", "#ef4444"),
}


class SlackChannel(BaseChannel):
    name = "slack"

    def is_configured(self) -> bool:
        return bool(settings.NORA_HOME_SLACK_BOT_TOKEN or settings.NORA_HOME_SLACK_WEBHOOK_URL)

    def send(self, notification, delivery) -> dict:
        if not self.is_configured():
            raise ChannelError("Slack is not configured (no bot token or webhook URL).")

        target = self._target(notification)
        blocks = self._blocks(notification)
        text = f"{notification.title} — {notification.body}".strip(" —")

        if settings.NORA_HOME_SLACK_BOT_TOKEN:
            target = self._resolve_dm(target, notification.recipient)
            return self._send_via_api(target, text, blocks)
        return self._send_via_webhook(text, blocks)

    # ── targeting ──────────────────────────────────────────────────────────────
    def _target(self, notification) -> str:
        if notification.severity in {"alert", "critical"}:
            return settings.NORA_HOME_SLACK_ESCALATION_CHANNEL
        recipient = notification.recipient
        if recipient is not None:
            dm = recipient.slack_dm_channel or recipient.slack_user_id
            if dm:
                return dm
        return settings.NORA_HOME_SLACK_DEFAULT_CHANNEL

    def _resolve_dm(self, target: str, recipient) -> str:
        """Turn a Slack *user* id into a DM conversation id.

        `chat.postMessage` does accept a bare user id, but only once an IM with
        that person exists — otherwise it answers `channel_not_found`, which
        looks identical to a missing channel and sends you hunting in the wrong
        place. Opening the conversation explicitly is what makes the escalation
        ladder's DMs reliable on first contact.

        The result is cached on the member so this costs one extra API call per
        person, ever, rather than one per notification.
        """
        if not target.startswith(_USER_ID_PREFIXES):
            return target  # a #channel or an already-resolved D… conversation

        try:
            response = requests.post(
                SLACK_CONVERSATIONS_OPEN,
                headers={"Authorization": f"Bearer {settings.NORA_HOME_SLACK_BOT_TOKEN}"},
                json={"users": target},
                timeout=TIMEOUT,
            )
            payload = response.json() if response.content else {}
        except requests.RequestException as exc:
            raise ChannelError(f"Could not open a Slack DM: {exc}") from exc

        if not payload.get("ok"):
            code = payload.get("error", "?")
            help_text = SLACK_ERROR_HELP.get(code, "")
            detail = f" {help_text.format(target=target)}" if help_text else ""
            raise ChannelError(
                f"Could not open a Slack DM with {target} ({code}).{detail}")

        channel_id = payload.get("channel", {}).get("id", "")
        if channel_id and recipient is not None and not recipient.slack_dm_channel:
            # Remember it, so the next notification skips this round trip.
            type(recipient).objects.filter(pk=recipient.pk).update(
                slack_dm_channel=channel_id)
        return channel_id or target

    # ── rendering ──────────────────────────────────────────────────────────────
    def _blocks(self, notification) -> list[dict]:
        emoji, _ = SEVERITY_STYLE.get(notification.severity, SEVERITY_STYLE["info"])
        blocks: list[dict] = [{
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"{emoji} *{notification.title}*"},
        }]
        if notification.body:
            blocks.append({"type": "section",
                           "text": {"type": "mrkdwn", "text": notification.body[:2900]}})

        context_bits = [f"_{notification.app_slug}_"]
        if notification.recipient:
            context_bits.append(str(notification.recipient.name))
        blocks.append({"type": "context",
                       "elements": [{"type": "mrkdwn", "text": " · ".join(context_bits)}]})

        elements: list[dict] = []

        if notification.url:
            base = (settings.ALLOWED_HOSTS[0] if settings.ALLOWED_HOSTS else "nora_home.home")
            href = notification.url if notification.url.startswith("http") \
                else f"http://{base}{notification.url}"
            elements.append({
                "type": "button",
                # Named explicitly: Slack generates a random action_id when one
                # is absent, and a log line reading "no handler for '68IXC'" is
                # a worse thing to debug than it needs to be. Nothing dispatches
                # on it — slack_socket ignores link buttons by their `url`.
                "action_id": "open_in_nora_home",
                "text": {"type": "plain_text", "text": "Open in Nora Home"},
                "url": href,
            })

        elements.extend(self._interactive_elements(notification))
        if elements:
            blocks.append({"type": "actions", "elements": elements})
        return blocks

    def _interactive_elements(self, notification) -> list[dict]:
        """Buttons and menus an app asked for, via `slack_actions` in the
        notification's context.

        Deliberately generic. This is Level 1 and must not learn what a "task"
        is — an app passes `slack_actions=[…]` to `notify()` and owns both the
        wording and the `action_id` its own handler is registered under
        (nora_home.notifications.slack_commands). That keeps the same seam the
        widget registry uses: apps supply data, the platform renders it.

        Anything malformed is dropped rather than raising: a bad button must
        cost its own button, not the whole notification.
        """
        elements: list[dict] = []
        for spec in (notification.context or {}).get("slack_actions") or []:
            if not isinstance(spec, dict) or not spec.get("action_id"):
                continue

            if spec.get("options"):
                elements.append({
                    "type": "static_select",
                    "action_id": spec["action_id"],
                    "placeholder": {"type": "plain_text",
                                    "text": str(spec.get("text", "Choose"))[:75]},
                    "options": [{
                        "text": {"type": "plain_text", "text": str(o.get("text", ""))[:75]},
                        "value": str(o.get("value", ""))[:150],
                    } for o in spec["options"][:100]],
                })
                continue

            button = {
                "type": "button",
                "action_id": spec["action_id"],
                "text": {"type": "plain_text", "text": str(spec.get("text", "?"))[:75]},
                "value": str(spec.get("value", ""))[:150],
            }
            # Slack rejects style:"default" outright — only primary and danger
            # are valid, and the absence of the key is what means "default".
            if spec.get("style") in {"primary", "danger"}:
                button["style"] = spec["style"]
            elements.append(button)
        return elements

    # ── transports ─────────────────────────────────────────────────────────────
    def _send_via_api(self, target: str, text: str, blocks: list[dict]) -> dict:
        try:
            response = requests.post(
                SLACK_API,
                headers={"Authorization": f"Bearer {settings.NORA_HOME_SLACK_BOT_TOKEN}",
                         "Content-Type": "application/json; charset=utf-8"},
                json={"channel": target, "text": text, "blocks": blocks},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise ChannelError(f"Slack request failed: {exc}") from exc

        payload = response.json() if response.content else {}
        if not payload.get("ok"):
            code = payload.get("error", "?")
            help_text = SLACK_ERROR_HELP.get(code, "")
            detail = f" {help_text.format(target=target)}" if help_text else ""
            raise ChannelError(f"Slack rejected the message ({code}).{detail}")
        return {"target": target, "ref": payload.get("ts", "")}

    def _send_via_webhook(self, text: str, blocks: list[dict]) -> dict:
        try:
            response = requests.post(settings.NORA_HOME_SLACK_WEBHOOK_URL,
                                     json={"text": text, "blocks": blocks},
                                     timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise ChannelError(f"Slack webhook failed: {exc}") from exc
        if response.status_code >= 300:
            raise ChannelError(f"Slack webhook returned {response.status_code}")
        return {"target": "webhook", "ref": ""}
