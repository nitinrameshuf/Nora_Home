# Notifications — `nora_home.notifications`

## What it is

Getting a message to a person, without the caller knowing or caring how. An app
says *"tell Nitin this, it's a warning"*; the platform decides the transport from
the recipient's preferences, their quiet hours, and the severity.

Channel-agnostic from the start, deliberately: it is what lets Slack cover urgent
delivery while iOS background push stays an open gap
([`../../CLAUDE.md`](../../../CLAUDE.md) § 5).

## Status

**Built; Slack partly proven.** In-app and wall delivery work. A real bot token
arrived 2026-08-04 and the house authenticates against the live workspace
(`auth.test` OK — team *Puffin Robotics*, bot `nora_home`), but **no message has
been delivered yet**: the token's scopes do not allow it. See § Slack setup.

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
| `sound` | The 24"'s speakers. **The one channel that cannot deliver anything itself** — the speakers are on the host and Django is in a container, so it writes audio to a bind-mounted cache and a systemd timer on the host runs `aplay`. Two sources: a Todo task's alarm, or spoken text (below) |
| `console` | Development |

**Quiet hours** are per-member and are ignored at `alert` and above. Duplicate
suppression is by `dedupe_key` within a window, so a sweep that runs every five
minutes does not produce twelve messages an hour.

## Speech

The house has a voice. `nora_home.notifications.speech.speak("...")` is the whole
published surface; Todo's `alarm_kind="speech"` goes through the same provider.

**Two layers, deliberately.** `tts.py` is the vendor — `TTSProvider.synthesize()`
takes text and returns `(bytes, content_type)`, and nothing above it knows which
company produced the audio. `speech.py` is the house: it checks quiet hours,
queues through `notify_house(channels=["sound"])`, and lets `SoundChannel` get the
audio to the host. An app that reached for the provider directly would get correct
audio, inside a container, at 3am, that nobody would ever hear.

**The text travels in `Notification.context`, never the audio.** `context` is a
`JSONField` and raw WAV does not survive the round trip, so synthesis happens on
*delivery*, in the worker — the same reason a task's alarm is re-resolved there
rather than at queue time.

Story 38 shipped only the seam and a stub that raised, on purpose. Groq's Orpheus
was wired in on 2026-08-07 and **no call site changed**, which is what the seam was
for. It was chosen because it needs no local model, no GPU and no audio toolchain
on the Pi — HTTPS in, WAV out, and WAV specifically because the host's `aplay`
plays it natively.

With `NORA_HOME_TTS_PROVIDER=none` (the shipped default) the house still boots and
still runs every reminder; only *spoken* alarms go quiet. A missing key is a
configuration gap, never an exception on the reminder path.

## What it offers other apps

`nora_home.notifications.api` — `notify()`, `notify_house()`.
`nora_home.notifications.speech` — `speak()`. Signatures in
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
| `NORA_HOME_TTS_PROVIDER` | `none` (default) or `groq` — whether the house has a voice |
| `NORA_HOME_GROQ_API_KEY` | Groq key, for the `groq` provider |
| `NORA_HOME_TTS_MODEL` / `NORA_HOME_TTS_VOICE` | Orpheus model and voice (`hannah` by default; also autumn, diana, austin, daniel, troy) |
| `NORA_HOME_ALARM_CACHE_DIR` | Where `SoundChannel` writes; must match the bind mount in `docker-compose.yml` |

Secrets live in `.env` only, never the database — a shared dump carries no tokens.

## Known gaps

- **Slack delivery is blocked on workspace permissions, not on code.** The token
  authenticates; posting fails with `channel_not_found` because the bot has not
  joined the channels and lacks `chat:write.public`, and DMs are impossible
  without `im:write`. No `HouseMember` has `slack_user_id` set either. See below.
- No iOS background push. Slack is the answer for anything urgent.
- The `display` channel silently dropped every message for a while after the wall
  was rebuilt around an iframe — the banner handler was missing from
  `wall-live.js`. Fixed 2026-08-03; worth knowing the failure mode, since the bus
  accepts anything and the browser ignores what it has no handler for.

## Slack setup

The bot token is the preferred path (webhooks cannot DM, and the escalation
ladder is built around DMing one person before telling the house).

**Scopes**, added in the Slack app config — the app must be **reinstalled** after
adding any of them:

| Scope | Without it |
|---|---|
| `chat:write` | Nothing can be posted at all |
| `chat:write.public` | Can only post to channels the bot was `/invite`d to |
| `im:write` | **No DMs** — every personal nudge falls back to the house channel |
| `users:read` | `manage.py slack_members` cannot list the workspace |
| `users:read.email` | Optional; lets `--auto` match members by email |

**Then link people**, because personal notifications target
`HouseMember.slack_user_id`:

```bash
manage.py slack_members                      # workspace vs household
manage.py slack_members --auto               # link on email, then on name
manage.py slack_members --link nitin=U01ABC  # by hand
manage.py slack_members --test nitin         # send a real DM
```

`--auto` refuses to guess when more than one Slack person matches: an ambiguous
link would quietly send someone else's reminders to the wrong person.

**Two environment traps**, both real, both now noted in `.env.example`:

- **Do not quote the token.** Compose passes `env_file` values through
  literally, so `NORA_HOME_SLACK_BOT_TOKEN="xoxb-…"` sends a token starting with
  a `"` character.
- **Recreate the container after editing `.env`.** A running container keeps the
  environment it started with, so the app sees the old value — or none.

**Reading Slack's errors.** They are accurate and useless: `channel_not_found`
means both "no such channel" *and* "the bot was never invited". `SlackChannel`
maps the common codes to the action that fixes them (`SLACK_ERROR_HELP`), and
keeps the raw code alongside.

**DMs open a conversation first.** `chat.postMessage` accepts a bare user id,
but only once an IM exists — otherwise it returns `channel_not_found` too. The
channel calls `conversations.open` and caches the result in
`HouseMember.slack_dm_channel`, so it is one extra API call per person ever.

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
