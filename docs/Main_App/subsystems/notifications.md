# Notifications — `nora_home.notifications`

## What it is

Getting a message to a person, without the caller knowing or caring how. An app
says *"tell Nitin this, it's a warning"*; the platform decides the transport from
the recipient's preferences, their quiet hours, and the severity.

Channel-agnostic from the start, deliberately: it is what lets Slack cover urgent
delivery while iOS background push stays an open gap
([`../../CLAUDE.md`](../../../CLAUDE.md) § 5).

## Status

**Built, unproven.** No Slack token has ever been available, so not one message has
been delivered to a real Slack workspace. In-app and wall delivery work.

## Models

| Model | Holds |
|---|---|
| `Notification` | title, body, severity, recipient, app_slug, url, dedupe key, context |
| `Delivery` | One attempt on one channel — status, timestamps, provider ref, retries |
| `Severity` | Choices: `info`, `nudge`, `warning`, `alert`, `critical` |

Two tables on purpose: one notification fans out to several channels, and each has
its own success or failure. That is what makes *"did the escalation actually
reach anyone"* answerable.

## Channels

| Channel | Notes |
|---|---|
| `slack` | Bot token **or** webhook. The token path gives DMs and threading, which the escalation ladder is designed around |
| `inapp` | The bell in the topbar, over websocket |
| `display` | A banner across the top of the 24" wall |
| `console` | Development |

**Quiet hours** are per-member and are ignored at `alert` and above. Duplicate
suppression is by `dedupe_key` within a window, so a sweep that runs every five
minutes does not produce twelve messages an hour.

## What it offers other apps

`nora_home.notifications.api` — `notify()`, `notify_house()`. Signatures in
[`../cross-functionality.md`](../cross-functionality.md#notifications).

Rendered manually in the sidebar as **Alerts** with an unread badge, above the
registry-driven nav loop.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `deliver_notification` | on demand | Sends one notification across its channels |
| `retry_failed_deliveries` | periodic | Retries transient failures with backoff |

## Settings

| Key | For |
|---|---|
| `NORA_HOME_SLACK_BOT_TOKEN` | Preferred Slack path — DMs and threading |
| `NORA_HOME_SLACK_WEBHOOK_URL` | Simpler alternative: one channel, zero setup |
| `NORA_HOME_SLACK_DEFAULT_CHANNEL` | Where house-wide messages go |
| `NORA_HOME_SLACK_ESCALATION_CHANNEL` | Where the top of the ladder shouts |
| `NORA_HOME_NOTIFICATION_CHANNELS` | Which channels exist at all |
| `NORA_HOME_NOTIFICATION_DEFAULT_CHANNELS` | Default set, currently `inapp,slack` |

Secrets live in `.env` only, never the database — a shared dump carries no tokens.

## Known gaps

- Never tested against live Slack. Open question: bot token or webhook.
- No iOS background push. Slack is the answer for anything urgent.
- The `display` channel silently dropped every message for a while after the wall
  was rebuilt around an iframe — the banner handler was missing from
  `wall-live.js`. Fixed 2026-08-03; worth knowing the failure mode, since the bus
  accepts anything and the browser ignores what it has no handler for.

## Files

```
models.py           Notification, Delivery, Severity
api.py              notify(), notify_house()
channels/slack.py   bot token or webhook
channels/inapp.py   the topbar bell
channels/display.py the 24" wall banner
channels/console.py development
tasks.py            deliver, retry
```
