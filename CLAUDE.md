# CLAUDE.md — Nora Home

**Read this first.** It is the handover document: what this is, where it stands, why
things are the way they are, and what to do next. If you are an AI agent picking this
repo up on a fresh machine, everything you need is here or linked from here.

Companion documents:
- [`DEVELOPMENT.md`](DEVELOPMENT.md) — how to **write an app** for this system. Point
  a family member's agent at that file, not this one.
- [`docs/`](docs/) — the project's record of itself. See §0 below: **updating it is
  part of every change, not a separate chore.**

---

## 0. Documentation duty — read before you write code

`docs/` is not a nice-to-have. It is how this project survives being picked up on a
different machine, by a different agent, weeks later. **Documentation changes ship in
the same commit as the code they describe.** A commit that changes behaviour and
leaves the docs stale is an incomplete commit.

| You changed… | Update, in the same commit |
|---|---|
| A story's status, or added one | [`docs/dashboard/nora_home_dashboard.html`](docs/dashboard/nora_home_dashboard.html) — the `STORIES` object, the summary counts, and the phase bars |
| Anything at all, in a working session | [`docs/progress.md`](docs/progress.md) — a dated entry, newest at the bottom |
| A component, boundary, or data flow | [`docs/architecture.md`](docs/architecture.md) — including the Mermaid diagrams |
| Something the family can now *do* | [`docs/capabilities.html`](docs/capabilities.html) — plain language, no jargon |
| A deployment, install, or uninstall step | [`docs/deployment.html`](docs/deployment.html) — for people, not agents; keep it in sync with `scripts/install-pi.sh`, the `Makefile`, `install_app`, and `uninstall_app` |
| The design language | [`docs/design-options.html`](docs/design-options.html) |
| A decision worth not re-litigating | §4 here, **and** the Decisions tab of the dashboard |

The dashboard is the main view — the same shape as the Nora robot project's, so both
read alike. Its story data lives in one `STORIES` object near the bottom of the file;
edit that and the cards follow.

**Status vocabulary**, used identically in the dashboard and `progress.md`:

| Status | Means |
|---|---|
| Complete | Written, reviewed, **and observed working** |
| Built, unproven | Written and reviewed, never executed against real infrastructure |
| Next | The immediate next piece of work |
| Planned | Agreed, not started |
| Retired | Explored and superseded — kept, with the reason |

Do not mark something Complete because the code looks right. Eight stories currently
sit at *built, unproven* precisely because that distinction is load-bearing.

---

## 1. What this is

Nora Home is the house operating system for a family. It runs on a **Raspberry Pi 5
(8GB)** and is on all the time. It is a Django **platform**, not an application: the
value is that family members (and their AI agents) can drop new apps into it and get
scheduling, reminders, escalation, notifications, AI, charts, storage, and a place on
the wall display for free.

> ### Nora Home is not Nora
>
> **Nora is the family's robot** — a separate machine with its own repository, its own
> voice, and its own project. **Nora Home is the house system** it lives alongside.
>
> Never use the bare name "Nora" for anything in this codebase. The package is
> `nora_home`, settings are `NORA_HOME_*`, CSS classes are `nh-`, the JS global is
> `NoraHome`, and the character on screen is *the home bot*. The AI system prompt
> states the distinction explicitly, because that is the one place the confusion
> would actually mislead a person.
>
> The two systems meet at **exactly two touchpoints**, both in
> [`docs/architecture.md`](docs/architecture.md) § Boundaries: the robot may
> `POST /api/homebot/say/` to put a line on the house screens, and it may read the
> MCP tools with a scoped device token. Nothing else is shared.

Planned apps — none of them built yet, all of them the *point*:

| Area | Examples |
|---|---|
| Self improvement | habits, reading, learning, journalling |
| Ambition | goals, milestones, weekly reviews |
| Family | diet, workout, beauty, skin care, health monitoring |
| Nora Robot | telemetry, task queue, training data, monitoring |
| House | maintenance schedules, consumables, repairs, bills |
| Integrations | Home Assistant, stock/portfolio, weather, calendars |

It is explicitly **not a todo list**. The tracker is one subsystem. The system is
meant to monitor automatically, escalate when things slip, hold long-term history,
and act as the second half of the Nora robot.

### Hardware
- Raspberry Pi 5, 8GB. Everything runs here in Docker.
- **HDMI-0 → 24" 1080p display**, always on, mounted on a wall. Read from ~3 metres.
- **HDMI-1 → 10.1" touchscreen**, kiosk mode. It is the *remote control* for the 24".
- Phones, iPads, and laptops hit the same server over the LAN.

---

## 2. Current state

**Phase: skeleton.** The platform is written; no family apps exist yet beyond one
reference implementation.

### Done
- Django project (`config/`) with dev / prod / pi settings layered on a shared base.
- **App registry** (`nora/core/registry.py`) — `NoraAppConfig` gives an app its URL
  mount, nav entry, dashboard widgets, wall panels, and MCP presence.
- **Tracker + escalation** (`nora/tracker/`) — trackables, materialized occurrences,
  completions, and a ladder that escalates owner → chain → adults → whole house.
- **Notifications** (`nora/notifications/`) — Slack (bot token *or* webhook), in-app,
  wall display, console. Delivery receipts and retries.
- **AI** (`nora/ai/`) — Claude via the Anthropic SDK, three model tiers, prompt
  caching on a shared house prefix, per-call cost accounting, a monthly budget cap.
- **MCP server** (`nora/mcpserver/`) — house data as agent tools, over stdio
  (`manage.py mcp_stdio`) and HTTP (`/mcp/`).
- **Datastores** (`nora/datastores/`) — Mongo helper, S3/MinIO helper, and
  `nora_backup` / `nora_restore` with a cross-engine migration path.
- **Displays** (`nora/displays/`) — the wall/kiosk bus over Channels, server-driven
  rotation, pinning, night mode.
- **Telemetry** (`nora/telemetry/`) — one time-series store for every number in the
  house, with thresholds that fire notifications.
- **Integrations** (`nora/integrations/`) — framework with scheduling, backoff, and
  failure alerting. No concrete integrations written yet.
- **Dashboard** (`nora/dashboard/`) — widget registry and per-member draggable layouts.
- **Deployment** — `docker-compose.yml`, `Makefile`, `scripts/install-pi.sh`.
- **Reference app** — `houseapps/example_habit/`.

- **Charts** — ECharts + Gridstack vendored in `static/nora_home/vendor/`, house chart
  theme in `static/nora_home/js/nh-charts.js`, grid in `static/nora_home/js/dashboard.js`.
- **Migrations** generated for every app and applied.

### Verified working
Run end to end on Windows against SQLite: `manage.py check` clean, migrations
applied, `bootstrap_home --demo` seeds three members and three habits, the server
boots under Daphne, login works, the home dashboard renders list/stat/chart widgets,
the widget picker adds and removes tiles, and the app registry mounts
`houseapps.example_habit` at `/habits/`.

### Verified on the Pi (2026-08-02)
`docker compose up -d --build` runs on real hardware against MySQL, Mongo,
RabbitMQ, and MinIO — `web` healthy, migrations and `bootstrap_home` running
automatically on container start. The wall (24" monitor) and kiosk (10.1"
touchscreen) both render correctly in Chromium kiosk mode on their own physical
screens, authenticated through the passwordless switcher, showing real app
content — not just code-reviewed, actually seen working. This needed one
environment-level fix beyond the app itself: Raspberry Pi OS's default desktop
session (`labwc`, Wayland) refuses to let anything reposition a fullscreen
window once placed, so both kiosk instances always ended up on the same
monitor regardless of any flag or tool. Switched the Pi to the X11 session
(`sudo raspi-config nonint do_wayland W1`, then reboot) instead, which honors
window placement the way `scripts/install-pi.sh` was written assuming, and the
whole problem disappeared. `install-pi.sh` now does this switch itself (§6 in
the script), so a reinstalled or fresh Pi picks it up automatically — no need
to rediscover it. One side effect worth knowing: Raspberry Pi Connect's
screen-share (Remote Desktop) only works on Wayland (it's built on `wayvnc`),
so it stops working once this switch happens — Pi Connect's Remote Shell and
plain SSH are unaffected and are the way to manage the Pi from here on.
Celery `worker`/`beat` came up but showed `unhealthy` in the one snapshot
taken — not dug into further, worth checking next time someone's on the Pi.

Re-verified the same day on a second, freshly-imaged Pi (the first one's
reliability had become suspect) — `install-pi.sh` hit **zero bugs** end to
end, confirming the fixes above actually held. One new thing found:
auto-login's "Unlock Login Keyring" dialog can appear more than once — a
second `gcr-prompter` instance blocked the kiosk's Chromium independently of
the one blocking the wall's — and genuinely blocks unattended boot until
dismissed by hand (`xdotool key Escape` after `windowactivate` worked;
clicking the Cancel button did not, twice). See item 7 below.

The kiosk's touchscreen also needed two fixes, both now resolved: the panel's
touch USB cable wasn't making a working connection to this Pi (swapping the
cable fixed it — confirmed by `lsusb`/`/proc/bus/input/devices` showing
nothing at all beforehand), and once detected, X11 needed an explicit
`TransformationMatrix` to map its touch coordinates onto just the kiosk's own
output — otherwise touch scales across the whole combined multi-monitor
desktop, since (unlike Wayland) X11 has no automatic per-output touch
mapping. Both are now permanent: `install-pi.sh` §8 writes
`/etc/X11/xorg.conf.d/40-touchscreen.conf` itself.

### Not done — pick up here
1. **Design system is unchosen.** `docs/design-options.html` has four directions
   rendered. The user is particular about UI and wants to approve one before it is
   built out. Until then `static/nora_home/css/nora-home.css` is the "Nightfall" direction.
   **Do not invest in visual polish before this is settled.**
2. **Celery worker/beat health unconfirmed.** Containers start, but showed
   `unhealthy` in `docker compose ps` at least once on the Pi — never confirmed a
   scheduled task (escalation sweep, backup) actually ran end to end.
3. **Slack, AI, MCP untested against live services.** No API keys were available.
4. **No tests.** `pytest` is configured; nothing is written.
5. **PWA manifest and service worker** — decided (§5) but not written.
6. **No favicon** — the logs show steady `/favicon.ico` 404s.
7. **Login keyring blocking unattended kiosk boot — fix applied, not yet
   re-verified.** Auto-login leaves the desktop's login keyring locked, so an
   "Unlock Login Keyring" dialog popped up over the wall and/or kiosk Chromium
   on first boot — sometimes once per screen — sitting there blocking that
   screen until dismissed by hand. Traced to Chromium itself: a fresh profile
   reaches for the OS keyring for its own credential storage, and since
   auto-login never unlocks that keyring, that reach always fails and prompts.
   Fixed by adding `--password-store=basic` to every launch script, which
   stops Chromium from touching the keyring at all. Not yet confirmed against
   a real reboot — the flag was added and reasoned through, but the next
   person on the Pi should watch first boot to confirm the dialog is actually
   gone before treating this as closed.

---

## 3. Getting it running

### On a laptop (no containers, SQLite)
```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows; use bin/activate elsewhere
pip install -r requirements/dev.txt
cp .env.example .env
python manage.py makemigrations
python manage.py migrate
python manage.py bootstrap_home --demo
python manage.py runserver
```
Then http://localhost:8000/home/ — no password anywhere; tap `nitin`, `partner`, or
`kid` in the switcher to sign in as them.

### On the Pi
```bash
make up        # first run: builds, migrates, bootstraps
make deploy    # every update after that
```

### First time on a new machine
```bash
git clone <repo> && cd nora-home
make up
```
`make up` creates `.env` from the example with a fresh secret key if it is missing.
`.env` is gitignored — secrets never enter the repo.

---

## 4. Decisions, and why

Read this section before changing architecture. Each of these was a real fork.

**Django over FastAPI/Node.** The admin alone is worth it: a family member can edit
an escalation policy or retime a job without a deploy. Batteries-included matters
more than raw speed on a home LAN.

**MySQL for relational, Mongo for documents, both.** Anything the tracker joins
across lives in MySQL. Journals, AI transcripts, and raw integration payloads go to
Mongo where the shape can change without a migration. Mongo is *optional* — the house
runs degraded, not broken, without it.

**RabbitMQ as the Celery broker, Redis for everything else.** RabbitMQ gives durable
queues and real routing so a runaway app task cannot delay an escalation. Redis is
cache + channel layer + rate limits. `NORA_HOME_BROKER_USE_REDIS=1` collapses this to
Redis-only for laptop work.

**Occurrences are materialized, not computed.** The tracker writes concrete rows two
weeks ahead. That is what makes "what did I miss last March" answerable and gives
escalation state somewhere to live.

**Escalation is a policy object, not code.** `EscalationPolicy.levels` is JSON, so
the ladder is editable in the admin. Three ship by default: House default, Gentle,
Safety critical.

**Secrets never go in the database.** `.env` only. Integration credentials are read
via `Integration.secret()` from the environment, so a database dump shared for
debugging carries no tokens.

**Apps mount at the URL root** — `/workout`, `/family`, `/maintenance`. The platform
lives under `/home`. `RESERVED_SLUGS` in `nora/core/registry.py` stops an app
claiming a platform prefix.

**Web app in kiosk mode, not a native app.** See §5.

**Apache ECharts + Gridstack.js, vendored, no build step.** ECharts because it
handles the whole range from sparkline to heatmap,
themes cleanly, and renders acceptably on a Pi. Gridstack for the draggable home
grid. Both are vendored into `static/nora_home/vendor/` rather than pulled from a CDN,
because the house must work with the internet down. **There is deliberately no npm,
no bundler, and no framework** — a family member's agent should be able to add a
chart without a toolchain, and the Pi should never run a build.

**Widgets return data, not HTML.** `ChartWidget.option()` returns an ECharts option
dict; the platform applies the house theme. This is what keeps every chart in the
house looking like the same system, no matter who wrote the app.

**Passwordless everywhere, including admin.** There is no password anywhere in this
system, on any surface — phone, laptop, wall, kiosk. A topbar switcher
(`templates/base.html`) lists the household; tapping a name logs you in as them via
`django.contrib.auth.login()` with no password check
(`nora_home/accounts/views.py`). A third tile, "Everyone", shows a combined view —
`DashboardLayout.Surface.SHARED` (`nora_home/dashboard/models.py`), which had sat
modeled but unused. `HouseMember.save()` now forces `is_staff`/`is_superuser` from
`role == admin`, so an admin-role member reaches `/admin/` the same way, no separate
gate. This was a deliberate choice, not an oversight: the house LAN is already
treated as the trust boundary everywhere else in this system (Slack tokens, MCP
device tokens, secrets all live at that boundary, not per-request), and a family
member — including a kid — shouldn't need to remember a password for an always-on
ambient display. Chosen explicitly over keeping a password on `/admin/` when asked.
`make member` now runs `add_member` (which sets an unusable password and an explicit
`--role`) instead of Django's `createsuperuser`, which used to make every house
member a superuser regardless of role — harmless while a password gated `/admin/`,
not once it doesn't.

---

## 5. Web app vs native kiosk app — answered

**Build it as a web app served locally, displayed full-screen by Chromium in kiosk
mode, and installable as a PWA on phones.** That is what `scripts/install-pi.sh`
configures.

Reasoning:
- One codebase covers the 24" wall, the 10.1" kiosk, phones, iPads, and laptops. A
  native app means four builds and four release processes for a house of four people.
- Chromium in `--kiosk` on the Pi *is* the full-screen app experience — no window
  chrome, no address bar, starts on boot. There is nothing a native shell adds here.
- Updates are `make deploy`. No app store, no sideloading, no version skew between
  the wall display and someone's phone.
- Adding a PWA manifest and a service worker gets home-screen install, an app icon,
  full-screen on iOS/Android, and offline-tolerant reads. That covers ~everything
  people actually want from "a real app".
- The one genuine gap is **background push on iOS**. Slack already covers urgent
  notification delivery, which is why the notification system was built
  channel-agnostic from the start.

Revisit only if the house needs Bluetooth, background location, or on-device ML from
a phone. Nothing planned needs those.

---

## 6. Conventions — follow these

**Migrations.** None are committed yet. Generate them once, commit them, and from
then on treat them as source: never delete or edit an applied migration; add a new
one. The Docker entrypoint runs `migrate` automatically on every web start, so a
committed migration is a deployed migration.

**Every model inherits from a base in `nora/core/models.py`** — `TimeStampedModel`
at minimum. `OwnedModel` when it belongs to a person, `SoftDeleteModel` when losing
it would hurt, `UUIDModel` when it is referenced from outside the database.

**Never import another app's models.** Use the published APIs
(`nora_home.tracker.api`, `nora_home.notifications.api`, `nora_home.telemetry.api`) or send a signal
from `nora_home.core.signals`. This is what lets an app be uninstalled without breaking
the house.

**No app reads `os.environ` directly.** Add the setting to
`config/settings/base.py` with a default, read it via `django.conf.settings`.

**Logging is structured.** `logging.getLogger(__name__)` and log normally; request
id, member, and surface are attached for you. Extra context goes in `extra={...}`.

**Failures degrade, never cascade.** A card that raises renders as "unavailable". A
broken house app is skipped at mount with a logged error. A dead Mongo is "degraded",
not "down". The wall display must survive anything.

**Comments explain why, not what.** Match the density already in the file.

---

## 7. Layout

```
config/            Django project: settings/, celery, urls, asgi, wsgi
nora/              the platform
  core/            registry, base models, cards, health, audit, logging, API
  dashboard/       widget base classes and per-member layouts
  accounts/        HouseMember (AUTH_USER_MODEL), roles, escalation contacts
  notifications/   channels (slack/inapp/display/console), delivery receipts
  tracker/         trackables, occurrences, scheduling, the escalation engine
  ai/              Claude client, model tiers, cost accounting
  mcpserver/       MCP tool registry, stdio server, HTTP transport
  datastores/      mongo, object storage, backup/restore commands
  displays/        wall + kiosk models, bus, consumers
  telemetry/       series, readings, rollups, thresholds
  integrations/    integration framework, scheduling, failure handling
  ui/              surface detection, Nora bot, theme
houseapps/         family apps live here (example_habit is the reference)
templates/         platform templates
static/nora_home/       css, js, vendor
docker/            entrypoint
scripts/           install-pi.sh
docs/              capabilities.html, design-options.html, deployment.html
```

---

## 8. Progress log

Append here. Newest last. Keep entries short and factual.

### 2026-07-31 — skeleton written and booted
- Platform apps, registry, tracker, escalation, notifications, AI, MCP, datastores,
  displays, telemetry, integrations, dashboard.
- Docker Compose stack, Makefile, Pi install script, `install_app` command.
- URLs restructured: platform under `/home`, house apps at the root (`/habits/`).
- Home screen is now a per-person grid of widgets from any app, with ECharts and
  Gridstack vendored for offline use.
- Migrations generated and applied; ran end to end on SQLite.
- Four design directions rendered in `docs/design-options.html` — awaiting a choice.

Two bugs worth remembering, both found only by actually running it:
- **The registry was silently empty.** Django picks an app's config by inspecting
  `AppConfig` subclasses in `apps.py`; because that file also imports `NoraAppConfig`
  there were always two candidates, and with no tie-breaker Django quietly fell back
  to a plain `AppConfig`. Fixed with `default = False` on the base plus
  `__init_subclass__` marking real configs — see `nora/core/registry.py`. If the nav
  and app directory ever go blank again, look there first.
- **Multi-line `{# #}` template comments render as visible text.** Django's `{# #}`
  is single-line only. Use `{% comment %}` blocks.

### 2026-07-31 — renamed away from the robot, and docs made first-class
- `nora` → `nora_home` everywhere: package, settings prefix, static path, CSS classes,
  JS globals, websocket routes, and the AI system prompt. See §1 and
  `docs/progress.md` for the full table of what moved.
- `docs/` established with a story dashboard (same shape as the robot project's),
  architecture diagrams, and a progress log. Documentation duty written into §0.
- First set of design directions rejected as too task-list-focused; a second,
  visualization-led set produced for review.

### 2026-07-31 — the third-party app-building path, actually tried
Asked "is this ready to hand to others to build apps inside it?" — rather than
answer from the code, actually played a new house-app author: cloned fresh,
followed `DEVELOPMENT.md`'s "Ten-minute start" literally, and hit two real bugs
that only showed up by doing it.

- **`install_app` couldn't generate migrations for the very first app added in a
  session.** `_migrate()` called Django's `makemigrations`/`migrate` in-process via
  `call_command()`, but the process's app registry was already populated — from
  the `.env` as it stood *before* `_register()` had just rewritten it — when the
  command started. Django never hot-reloads `INSTALLED_APPS` mid-process, so the
  new app was invisible to that call and it failed with `No installed app with
  label 'workout'`, silently, one step into the documented flow. Fixed by running
  `makemigrations`/`migrate`/`collectstatic` as fresh `manage.py` subprocesses
  instead, which re-read `.env` from scratch. Verified: re-ran the same scratch
  test with the fix and got `Applying workout.0001_initial... OK`.
- **The reference app refers to itself in far more places than the docs said.**
  Copying `houseapps/example_habit` and following the four documented steps
  (rename `apps.py`, write your own models, your own views/urls) produces a crash
  — `AlreadyRegistered: The model Habit is already registered with
  'example_habit.HabitAdmin'` — the first time the new app's `admin.py` runs,
  because seven files still say `from houseapps.example_habit import ...` and the
  templates live in a directory named after the old app. `DEVELOPMENT.md`'s
  "Ten-minute start" now opens with the actual mechanical fix (`grep -rl
  example_habit | xargs sed -i ...` plus the templates-directory rename) instead
  of leaving it to be discovered as a stack trace.
- Also replaced every Unicode arrow/checkmark/ellipsis/em-dash in
  `install_app.py`'s, `nora_restore.py`'s, and `bootstrap_home.py`'s
  `self.stdout.write()` calls with plain ASCII — they crashed with
  `UnicodeEncodeError` under a non-UTF-8 console/pipe context on Windows. Found
  one instance first (a checkmark), fixed only that one, then hit a second
  (an arrow) while testing the git-clone path below — so all `stdout.write()`
  calls across the management commands were grepped and fixed together instead
  of one at a time.

**Then closed the one gap left open at the end of that session**: `install_app`'s
git-clone acquisition path (`_from_git`) had never actually been run, only its
local-path sibling. Built a real local git repo, cloned it through the actual
`_from_git`/`_verify`/`_register`/`_migrate` pipeline (bypassing only the CLI's
`http(s)://`/`git@` scheme sniff, which a `file://` test URL can't satisfy), and
confirmed both the clone-and-strip-`.git` mechanics and the `nora-<name>` →
`<name>` prefix-stripping convention shown in the command's own docstring —
`nora-plants` correctly became `houseapps.plants`.

**All of this was verified by redoing the exact failing scenarios afterward**, not
just read over: fresh clones, corrected rename recipe, `install_app` via both the
local-path and git-clone routes, `manage.py check` clean, servers boot, every
app's URL routes correctly, each new app appears in `list_apps` with its own
widgets and its own generated migration applied.

---

## 9. Open questions for the user

Ask before assuming.

1. **Which design direction?** Blocking any real UI work (Story 23). See
   `docs/design-options.html` — the second, visualization-led set. The first set was
   rejected for looking like a todo app.
2. **Slack: bot token or webhook?** A bot token gives DMs and threading, which the
   escalation ladder is designed around. A webhook is one channel and zero setup.
   The code supports both; the token path is better.
3. **Which app first?** The skeleton needs one real app to prove itself. House
   maintenance is the best candidate — it exercises long cadences, escalation, and
   the wall display without needing anyone's health data.
4. **Repo hosting and remote?** `scripts/install-pi.sh` needs `NORA_HOME_REPO` set.
