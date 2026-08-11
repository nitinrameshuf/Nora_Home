# CLAUDE.md — Nora Home

**Read this first.** It is the handover document: what this is, where it stands, why
things are the way they are, and what to do next. If you are an AI agent picking this
repo up on a fresh machine, everything you need is here or linked from here.

Companion documents:
- [`docs/Main_App/DEVELOPMENT.md`](docs/Main_App/DEVELOPMENT.md) — how to **write an
  app** for this system. Point a family member's agent at that file, not this one.
- [`docs/Main_App/cross-functionality.md`](docs/Main_App/cross-functionality.md) —
  the index of what every app can call from every other app.
- [`docs/Main_App/testing.md`](docs/Main_App/testing.md) — **how to verify your own
  work on the real hardware**, including SSH access to the Pi.
- [`docs/`](docs/) — the project's record of itself. See §0 below: **updating it is
  part of every change, not a separate chore.**

---

## 0. Documentation duty — read before you write code

`docs/` is not a nice-to-have. It is how this project survives being picked up on a
different machine, by a different agent, weeks later. **Documentation changes ship in
the same commit as the code they describe.** A commit that changes behaviour and
leaves the docs stale is an incomplete commit.

### How `docs/` is organised

Three folders, by **who the document is for**. See [`docs/README.md`](docs/README.md).

| Folder | For | Holds |
|---|---|---|
| [`docs/User/`](docs/User/) | People, not agents | `deployment.html`, and `dashboard/` — the story board |
| [`docs/Main_App/`](docs/Main_App/) | The Django platform and its infrastructure | `DEVELOPMENT.md`, `cross-functionality.md`, `architecture.md`, `testing.md`, `progress.md`, and `subsystems/` — one file per platform subsystem |
| [`docs/House_Apps/`](docs/House_Apps/) | The family's own apps | One folder per app, named after its module, holding all of that app's docs |

**Every house app is required to have a folder under `docs/House_Apps/` holding
`requirements.md`, `README.md`, and `testing.md`.** `install_app` warns when any is
missing and `tests/test_house_apps.py` fails without them, so it is enforced rather
than merely stated.

**Building a house app has three gates**, in order — see
[`docs/Main_App/DEVELOPMENT.md`](docs/Main_App/DEVELOPMENT.md#the-workflow--three-gates-in-order):

1. **Requirements first.** `requirements.md` describes what the app does in plain
   language, and **the user approves that functionality before any code is
   written.** Do not start with code.
2. **Development is not done until it is tested and integrated.** Unit tests for
   the app's own logic, plus verified integration with the platform (todo,
   notifications, telemetry, widgets, nav, kiosk), with the whole suite green.
3. **Deployed to the Pi and confirmed over SSH.** Until then it is *built,
   unproven*, never Complete.

### What to update, when

| You changed… | Update, in the same commit |
|---|---|
| A story's status, or added one | [`docs/User/dashboard/nora_home_dashboard.html`](docs/User/dashboard/nora_home_dashboard.html) — the `STORIES` object, the summary counts, and the phase bars. **Cards are hand-authored HTML per phase; the `STORIES` object only feeds the modal.** Adding a story means both. |
| **Anything a person sees** | [`docs/Main_App/ui-overhaul-mockup.html`](docs/Main_App/ui-overhaul-mockup.html) — **the UI/UX reference. Change it first, show it, get approval, then write code.** See §4 |
| Anything at all, in a working session | [`docs/Main_App/progress.md`](docs/Main_App/progress.md) — a dated entry, newest at the bottom |
| A component, boundary, or data flow | [`docs/Main_App/architecture.md`](docs/Main_App/architecture.md) — including the Mermaid diagrams |
| One subsystem's models, API, tasks, or gaps | The matching file in [`docs/Main_App/subsystems/`](docs/Main_App/subsystems/) |
| A published cross-app function | **Nothing by hand.** Run `manage.py sync_docs` — the tables in [`cross-functionality.md`](docs/Main_App/cross-functionality.md) and `DEVELOPMENT.md` are generated between `sync_docs` markers, and `tests/test_docs_in_sync.py` fails when they drift |
| The app contract, or anything about the five surfaces | [`docs/Main_App/DEVELOPMENT.md`](docs/Main_App/DEVELOPMENT.md) |
| Anything at all — add or update a test | `tests/test_<subsystem>.py`, and a house app's own `tests/test_<app>.py` |
| The app contract — a new declaration or surface | `tests/contract_app/` and `tests/test_app_contract.py`, so the promise stays executable |
| How you verify work on the Pi, or what the suite covers | [`docs/Main_App/testing.md`](docs/Main_App/testing.md) |
| A house app | That app's folder in [`docs/House_Apps/`](docs/House_Apps/) |
| A deployment, install, or uninstall step | [`docs/User/deployment.html`](docs/User/deployment.html) — for people, not agents; keep it in sync with `./nora`, `scripts/lib/provision-pi.sh`, `install_app`, and `uninstall_app` |
| A decision worth not re-litigating | §4 here, **and** the Decisions tab of the dashboard |

The dashboard is the main view — the same shape as the Nora robot project's, so both
read alike. Its story data lives in one `STORIES` object near the bottom of the file;
edit that and the cards follow.

`CLAUDE.md` stays at the repo root, not in `docs/`: it is loaded automatically from
there by agent tooling, and moving it would stop it being read.

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
> [`docs/Main_App/architecture.md`](docs/Main_App/architecture.md) § Boundaries: the robot may
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

It is explicitly **not a todo list**. Todo is one subsystem. The system is
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
- ~~**Tracker + escalation** (`nora/tracker/`)~~ — **deleted 2026-08-06 (Story
  40).** Todo absorbed it: scheduling and the escalation ladder carried over
  rather than being rewritten, and `EscalationPolicy` is now a Todo model,
  moved with its rows and primary keys intact. See §4's migration decision.
- **House log** (`/home/log/`, `nora/core/houselog.py`) — audit events, health
  transitions, notifications, failed deliveries, integration failures and
  telemetry breaches on one filterable timeline. Built on one rule: **record
  what changed, not what ran** — the module docstring carries the measurements
  that forced it.
- **Todo** (`nora_home/todo/`) — **Level 2**, the app the base leans on for
  scheduling, reminders and escalation. Priority-column board, calendar, full-text
  search with saveable filters, labels, shared tasks with owner/assignee/approver,
  reminders and a ported escalation ladder, a Reporting page and tone presets,
  and a system-tasks board fed by telemetry thresholds and failing
  integrations, all with a real front end at `/todo/` and a two-level kiosk
  screen (all five documented buttons now exist). **Phase 7 is complete — 15
  of 15 stories built**, including Slack in both directions: reminders arrive
  as DMs with Done/Skip/Snooze/Reassign buttons, and `/todo` answers back over
  Socket Mode. **Full design, decision log, and per-story "as built" notes**:
  [`docs/Main_App/subsystems/todo.md`](docs/Main_App/subsystems/todo.md).
  Story-by-story status: the dashboard. **Stories 35 and 36 have run on the Pi
  against MySQL** — Reporting, settings and the system board all rendered
  there, the priority-mix query and the system-task dedupe both checked against
  MySQL specifically, and each seen on the physical wall and kiosk through the
  kiosk's own navigation. Stories 28–34 and 42 have still only run against
  SQLite on a laptop. **Story 41 (Tests, Docs & Deploy) closed the phase**:
  87 new browser tests (`tests/qa/test_todo_qa.py`), and found two real
  accessibility bugs the whole session's worth of unit tests never could —
  see the dated entry below.
- **Notifications** (`nora/notifications/`) — Slack (bot token *or* webhook), in-app,
  wall display, console. Delivery receipts and retries.
- **AI** (`nora/ai/`) — Claude via the Anthropic SDK, three model tiers, prompt
  caching on a shared house prefix, per-call cost accounting, a monthly budget cap.
- **MCP server** (`nora/mcpserver/`) — house data as agent tools, over stdio
  (`manage.py mcp_stdio`) and HTTP (`/mcp/`).
- **Datastores** (`nora/datastores/`) — Mongo helper, S3/MinIO helper, and
  `nora_backup` / `nora_restore` with a cross-engine migration path.
- **Displays** (`nora/displays/`) — the wall/kiosk bus over Channels. The 24" wall
  shows the real app (`/home/`) through a live iframe; the 10.1" kiosk is a
  context-sensitive button remote that drives it — each app can declare its own
  kiosk control screen via `nora_kiosk_controls`. A Settings tab holds a schedule
  for powering both screens off overnight.
- **Telemetry** (`nora/telemetry/`) — one time-series store for every number in the
  house, with thresholds that fire notifications.
- **Integrations** (`nora/integrations/`) — framework with scheduling, backoff, and
  failure alerting. No concrete integrations written yet.
- **Dashboard** (`nora/dashboard/`) — widget registry and per-member draggable layouts.
- **Deployment** — `./nora` (the runner: install, up, upgrade, backup, restore,
  apps, screens, uninstall), `docker-compose.yml`, `scripts/lib/provision-pi.sh`. An
  `nginx` service terminates TLS on `:443` (self-signed — see §4) and is the only
  published entry point; Daphne's `:8000` is internal-only.
- **Charts** — ECharts + Gridstack vendored in `static/nora_home/vendor/`, house chart
  theme in `static/nora_home/js/nh-charts.js`, grid in `static/nora_home/js/dashboard.js`.
- **Migrations** generated for every app and applied. One of them,
  `todo/0007_escalationpolicy_from_tracker`, is worth knowing about before you
  touch Todo's history — see §4.

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
window placement the way `scripts/lib/provision-pi.sh` was written assuming, and the
whole problem disappeared. `provision-pi.sh` now does this switch itself (§6 in
the script), so a reinstalled or fresh Pi picks it up automatically — no need
to rediscover it. One side effect worth knowing: Raspberry Pi Connect's
screen-share (Remote Desktop) only works on Wayland (it's built on `wayvnc`),
so it stops working once this switch happens — Pi Connect's Remote Shell and
plain SSH are unaffected and are the way to manage the Pi from here on.
Celery `worker`/`beat` came up but showed `unhealthy` in the one snapshot
taken — not dug into further, worth checking next time someone's on the Pi.

### Verified on the Pi (2026-08-02, continued) — kiosk-as-remote-control
The 24" was repointed from the old passive ambient view to the real app, and the
10.1" kiosk was rebuilt into a context-sensitive remote for it — tapping an app's
tile switches what the wall shows *and* swaps the kiosk to that app's own control
buttons, declared per app via `nora_kiosk_controls` (see `docs/Main_App/DEVELOPMENT.md`). A
Settings tab was added, its first setting a schedule for powering both screens off
overnight. Deployed and checked directly against the physical hardware, not just
`manage.py check`: simulated touch (`xdotool`) confirmed tapping a kiosk tile
navigates the wall's iframe and switches the kiosk's own screen, and that the
kiosk's back button returns to its main menu without disturbing the wall. Three
real, hardware-only bugs surfaced this way: DPMS (`xset dpms force`) blanks *both*
screens together, not just the wall — confirmed with the user and accepted, since
per-output control (`xrandr --off`) had already proven fragile earlier in this
project; the Pi's `.env` still carried `.env.example`'s placeholder timezone
(`America/Los_Angeles` instead of the real `America/New_York`), now fixed and
auto-detected by `provision-pi.sh` via `timedatectl`; and a CSS specificity bug
(`.kiosk-grid` vs. the browser's own `[hidden]` rule) let a tapped app's control
screen render on top of the main menu instead of replacing it, fixed in
`static/nora_home/css/displays.css`.

Re-verified the same day on a second, freshly-imaged Pi (the first one's
reliability had become suspect) — `provision-pi.sh` hit **zero bugs** end to
end, confirming the fixes above actually held. One new thing found:
auto-login's "Unlock Login Keyring" dialog can appear more than once — a
second `gcr-prompter` instance blocked the kiosk's Chromium independently of
the one blocking the wall's — and genuinely blocks unattended boot until
dismissed by hand (`xdotool key Escape` after `windowactivate` worked;
clicking the Cancel button did not, twice). Traced to Chromium itself: a
fresh profile reaches for the OS keyring for its own credential storage,
and since auto-login never unlocks that keyring, the reach always fails and
prompts. Fixed with `--password-store=basic` on every launch script, which
stops Chromium from touching the keyring at all — confirmed with a genuinely
fresh throwaway profile producing no dialog and no `gcr-prompter` process,
not just reasoned through.

Two more one-click gaps closed the same day: `scripts/lib/pre-provision-pi.sh`
(run once via `sudo`, grants a validated `NOPASSWD` sudoers entry so nothing
in `provision-pi.sh` prompts for a password afterward — no new capability, the
account already has full sudo, this just removes the prompt), and the
Docker-install step no longer exits asking for a manual re-login — it
re-execs itself under `sg docker -c` and continues in the same run instead
(logic reviewed carefully, not yet re-tested against a genuinely fresh
install since Docker was already present on the last Pi provisioned).

The kiosk's touchscreen also needed two fixes, both now resolved: the panel's
touch USB cable wasn't making a working connection to this Pi (swapping the
cable fixed it — confirmed by `lsusb`/`/proc/bus/input/devices` showing
nothing at all beforehand), and once detected, X11 needed an explicit
`TransformationMatrix` to map its touch coordinates onto just the kiosk's own
output — otherwise touch scales across the whole combined multi-monitor
desktop, since (unlike Wayland) X11 has no automatic per-output touch
mapping. Both are now permanent: `provision-pi.sh` §8 writes
`/etc/X11/xorg.conf.d/40-touchscreen.conf` itself.

### Verified on the Pi (2026-08-03) — HTTPS on :443, via nginx
Asked directly ("why is it on :8000, what would it take to put it on 443")
led to a real change, not just an explanation: an `nginx` service now
terminates TLS and redirects plain HTTP; Daphne's `:8000` is no longer
published to the host at all. Self-signed cert
(`scripts/gen-self-signed-cert.sh` — no public domain exists for a house LAN
to get a CA-issued one), chosen explicitly over `mkcert`/a private CA or a
real domain with Let's Encrypt when asked directly. See §4's decision entry
for the one real trap this surfaced: `SECURE_HSTS_SECONDS` had to be
force-disabled in `config/settings/pi.py` regardless of `SECURE_SSL_REDIRECT`
— HSTS plus a self-signed cert would have permanently locked every browser
out the first time the cert ever changed.

Verified first locally via Docker Compose against real `config.settings.pi`
settings (HTTPS 200 with no HSTS header, HTTP→HTTPS redirect, `:8000`
unreachable from the host, `manage.py check --deploy` showing only the two
already-understood deliberate warnings, `/ws/` upgrades correctly relayed to
Channels) — a local bug surfaced and fixed there
(`gen-self-signed-cert.sh`'s `hostname -I` call aborting the script under
`set -e` on platforms where that flag doesn't exist), before ever touching
the Pi. Then deployed for real: cert generated on the Pi itself (its SAN
picked up the Pi's actual LAN IP automatically), the same checks repeated
directly on the Pi, and — the part that actually mattered — the wall and
kiosk's Chromium launch scripts, generated by an *earlier* run of
`provision-pi.sh` before this change, still pointed at the old
`http://localhost:8000` and had to be regenerated (re-running just
`provision-pi.sh`'s `launch_script()` function, not the whole script, to avoid
sudo prompts over a non-interactive session for already-satisfied steps).
Killed and relaunched both Chromium instances by exact PID, then
screenshotted both physical screens: the wall shows the real authenticated
`/home/` dashboard — House vitals widget included, confirming the whole
stack survived the restart, not just nginx — and the kiosk shows its normal
button grid, connected, with no certificate-warning interstitial on either
screen (`--ignore-certificate-errors` did its job).

### Verified on the Pi (2026-08-07) — the observe pass, and the house's voice

**Story 41 was marked Complete before this was done, and that was wrong.** The
87 browser tests were real and green, but §13.4 is explicit that the phase is
not Complete until four things are *seen*, and none of them had been. The
database said so plainly when finally asked: **0 live tasks, 0 sound deliveries
ever.** The chime heard on 2026-08-06 was the host script invoked by hand, not
an alarm that travelled the pipeline. Recording this because the failure was not
the testing — it was calling something Complete on the strength of a green suite,
which is the exact distinction CLAUDE.md's status vocabulary exists to prevent.

All four are now observed, with three real tasks seeded on the family's board
(bins, water filter, boiler service — kept, not test litter):

| §13.4 | How it was seen |
|---|---|
| The board renders on the wall | Screenshotted: "Take the bins out" in red as overdue, all three cards, real due dates |
| The wall shows the chosen widgets | Same screenshot — Due next, Open now ("3 open"), the year heatmap, House health |
| A reminder arrives in Slack | `send_reminders()` run for real: `Delivery(channel="slack", status="sent")` |
| An alarm plays through the 24"'s speakers | A **speech** alarm: Groq synthesised it, `SoundChannel` wrote `36.wav` to the bind mount, the host timer played it |

**The house can speak** (`nora_home/notifications/speech.py`). Story 38 shipped
the TTS seam and a stub that raised, deliberately leaving the vendor unchosen;
Groq's Orpheus went in behind it on 2026-08-07 and **no call site changed** —
which is what the seam was for. `speak("...")` is the published API, callable
from any app; Todo's `alarm_kind="speech"` uses the same provider. Chosen because
it needs no local model, GPU or audio toolchain on the Pi: HTTPS in, WAV out, and
WAV specifically because the host's `aplay` plays it natively. With
`NORA_HOME_TTS_PROVIDER=none` the house still boots and still reminds — only
spoken alarms go quiet.

**One real bug this surfaced, worth more than the feature.** `env()` reads the
real environment and Compose passes every `.env` value into the container, so on
the Pi `./nora test` inherited the live `NORA_HOME_TTS_PROVIDER=groq` and **made
a billable API call inside a unit test.** It showed up only because two tests
asserting the degraded path started failing with genuine WAV bytes; written any
looser it would have been silent, and the suite would have been quietly spending
money and requiring network on every run. `config/settings/test.py` now forces
the TTS, Groq and Anthropic keys off rather than leaving them unset, and a test
asserts it so the next credential added cannot reopen the hole.

### Not done — pick up here
0. **Phase 7 — Todo, complete (15 of 15).** What is left is not another Todo
   story — it is **Story 24** (house maintenance, the first real family app,
   unblocked since Story 27), which is what actually proves the platform was
   worth building rather than another platform story. **Its `requirements.md`
   needs your approval before any code**, the first of DEVELOPMENT.md's three
   gates. Read [`docs/Main_App/subsystems/todo.md`](docs/Main_App/subsystems/todo.md)
   before touching Todo itself — it is the approved design and the record of
   every decision made building it; do not re-derive anything already settled
   there. `docs/Main_App/subsystems/todo-build-brief.md` is gone — it said to
   delete itself once the build finished, and Story 41 did. **Three things a
   fresh session needs to know before doing anything else:**
   - **`.env` and `db.sqlite3` were both briefly tracked in git; both are fixed
     now** (`.gitignore` reads `.env`/`.env.*` and `db.sqlite3`). While `.env`
     was tracked, `git pull` on the Pi replaced the house's real configuration
     with laptop defaults — see §4's decision entry for the diagnosis, which is
     worth keeping even though the specific cause is closed: the failure shape
     (a house that looks empty and has lost nothing) belongs to anything that
     changes `.env`, and the first instinct it provokes — restore from backup —
     would be the genuinely destructive move.
   - **Todo's schema is proven on MySQL; most of its behaviour is not.** All six
     todo migrations are applied on the Pi, `migrate --check` reports nothing
     outstanding, and the constraints are really there — including Story 42's
     `todo_no_approver_on_recurring`, which this file previously listed as
     unproven. Stories 35 and 36 were additionally exercised *as an app* against
     MySQL (Reporting, settings, the system board, the priority-mix query, the
     system-task dedupe, and all seen on the physical wall and kiosk). Stories
     28–34 and 42 have still only had their **behaviour** run against SQLite on
     a laptop — the tables exist on MySQL, but nobody has completed, skipped,
     approved or escalated anything there.
   - **Check `git status` before doing anything.** Stories were committed
     periodically through the session, not after every single one — confirm
     what has and hasn't landed before assuming the working tree matches HEAD.
   - **Story 40 left one gap open on purpose.** The tracker published
     `register_trackable()` — the call `DEVELOPMENT.md` tells a house-app author
     to make so the platform handles their due dates, nudges and escalation.
     Todo has no equivalent, so that recipe has no working call behind it right
     now. What it should look like on Todo's model is a design question, so it
     belongs to Story 24's requirements gate rather than to a deletion story.
     Do not invent one without agreeing the shape first.
1. **Design system chosen: "Almanac" — engine shipped and seen live on the Pi.**
   See §4's new decision entry and the design-options mockups (deleted 2026-08-03; see progress.md). The living
   background (season/day-night/weather composited behind the real app, never
   replacing it) is wired into `base.html` and `kiosk.html`, backed by a real
   weather integration (Open-Meteo, no API key). Verified locally (real fetch
   against the live API, `manage.py check` clean, key pages rendering with
   correct `data-season`/`data-daypart`/`data-weather`) and then deployed and
   screenshotted on the physical wall and kiosk the same session — real
   weather (cloudy, 24.8°C), correct season/daypart, both screens agreeing,
   and no regression to the kiosk-drives-wall remote-control flow. One real
   bug found doing this: `bootstrap_home`'s `_storage()` only caught
   `StorageUnavailable`, not this Pi's actual MinIO signature-mismatch error,
   so it was silently killing everything after it including the new
   integration-seeding step — fixed to degrade the same way the rest of the
   codebase treats object storage as optional. **Not yet built**: a full type
   scale and per-component restyle across all five surfaces (this pass only
   retrofit `.card`/`.sidebar`/`.kiosk-tile` to the glass material), and
   unverified: whether continuous
   animation plus backdrop blur holds up over hours rather than minutes.
2. ~~**Celery worker/beat health unconfirmed.**~~ **Resolved 2026-08-04.** Celery
   was never broken. `worker` and `beat` inherited the Dockerfile's HEALTHCHECK,
   which curls `localhost:8000` — the *web* role's port — so the check could
   never pass for a process that runs no HTTP server; it sat `unhealthy` with a
   473-long failing streak while the worker pongs instantly and beat dispatches
   on time. Both now have honest checks (`celery inspect ping`, and
   `/proc/1/cmdline` for beat, since `pgrep` is not in the slim image). Confirmed
   end to end: **279 health snapshots in the database, newest 5.5 minutes old**,
   which is beat → worker → DB working. All nine services now report healthy.
   The beat log did expose a real bug, though — see item 8.
3. ~~**Slack: token verified live, delivery blocked in the workspace.**~~
   **Resolved 2026-08-06, and Slack now works in both directions.** All scopes
   were granted and verified against the live API rather than assumed
   (`users:read` by resolving both members' Slack IDs back to their real
   names); `nitin` and `priya` have `slack_user_id` set. Story 37 then added
   the inbound half — Socket Mode, `/todo`, and buttons on the message. **Real
   reminders arrive as DMs and Done/Skip were tapped for real**, moving the
   instances in MySQL. See §12 of
   [`docs/Main_App/subsystems/todo.md`](docs/Main_App/subsystems/todo.md).

   Traps found along the way, all now guarded or documented: the bot token was
   once **quoted** in `.env` and Compose passes `env_file` values literally, so
   the app saw a leading `"`; a container had not been recreated after an edit,
   so it saw nothing at all; and notification *rendering* happens in the
   **worker**, so a `docker compose up -d web` alone ships a message with no
   buttons and no error. Slack's own error strings are useless for diagnosis
   (`channel_not_found` means both "no such channel" and "never invited"), so
   `SlackChannel` maps the common codes to the actual fix.

   The **app-level token** (`xapp-`, `connections:write`) is a third credential,
   distinct from the bot token *and* from Slack's "App Configuration Tokens"
   which expire every 12 hours and are for the manifest API — nothing here uses
   those. Only the `slack` container reads it.

   **AI and MCP remain untested against live services** — no keys supplied.
4. **Tests: 906, one file per subsystem, green.** `./scripts/run-tests.sh` (or
   `make test`; `make test-pi` runs it inside the container on the Pi). Runs in
   ~30s with no containers, no network, and no credentials — SQLite, in-memory
   channel layer, eager Celery — so it gives the same answer on a laptop and on
   the Pi. The root `conftest.py` prints a **fixed-size report** instead of
   pytest's output: one line per subsystem, one line per failure carrying only
   its assertion, with full tracebacks written to `logs/test-full.txt` for the
   rare case they are needed. That is deliberate — reading raw pytest back over
   SSH costs more than the information in it is worth. Still uncovered: Celery
   beat actually firing, Slack/AI/MCP against live services, Mongo/MinIO, and
   the websocket consumers. See
   [`docs/Main_App/testing.md`](docs/Main_App/testing.md) § Known gaps.
   **`./nora qa`** is the second layer: 226 checks driving a real Chromium
   against the running house — every page rendered and checked for console
   errors, the journeys clicked through, both screens open at once so a kiosk tap
   can be seen moving the wall, and contrast measured from pixels. ~8 minutes,
   run from a laptop, deliberately separate from the fast suite. It found two
   real bugs on its first run — a checkbox with no accessible name, and the
   light theme unreadable at dusk (2.06:1); **both fixed** — plus one about the
   tools: axe's colour-contrast rule is unusable against `backdrop-filter` over a
   living gradient, and believing it would have meant degrading readable text.
   Contrast is measured from pixels instead. **Story 41's 87 new Todo tests
   found two more the same way**: `.todo-card` had no glass pane at all, unlike
   every other surface in the house, measuring as low as 2.04:1 in dark theme —
   fixed with the same pane treatment every other card already has. This Mac has
   no Python or browser toolchain, so the suite runs on the Pi itself over SSH
   (`~/.nora-qa-venv`), not from a laptop — the one exception to "run from a
   laptop" that the hardware available actually allows.
5. **PWA manifest and service worker** — decided (§5) but not written.
6. **No favicon** — the logs show steady `/favicon.ico` 404s.
7. ~~**Kiosk-drives-wall redesign and the Settings tab — built, unverified.**~~
   **Resolved.** Both were verified on the physical screens — see §2's
   "Verified on the Pi (2026-08-02, continued)" note, and again on 2026-08-04
   when the kiosk was cleaned up. `xset dpms force off` does power the panel
   down, and it *is* session-wide rather than per-output: it blanks the kiosk
   too. That was confirmed with the user and accepted, since per-output
   `xrandr --off` had already proven fragile earlier in this project.
8. **The reference app taught the pattern the platform forbids** — `example_habit`
   imported the old `nora_home.tracker.models` in five files. **Fixed 2026-08-04**
   by adding the missing query helpers to that app's own API; both apps are gone
   now (Story 28 deleted the reference app, Story 40 the tracker), but the rule
   they proved is not, and `KNOWN_MODEL_IMPORT_DEBT` in `tests/test_house_apps.py`
   is still empty. Verified by actually copying the reference app into a scratch house app
   and running the contract tests against it: clean. If you are ever tempted to
   add an entry to that debt list, add the API function instead.

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
./nora install   # first time on a fresh Pi: Docker, both screens, systemd
./nora up        # start the house
./nora upgrade   # every update after that
./nora help      # everything else
```
Everything operational goes through **`./nora`** — one command, one help text.
It replaced `scripts/install-pi.sh` as the entry point; that provisioning still
exists unchanged at `scripts/lib/provision-pi.sh` and `./nora install` runs it.
`make` targets still work as thin aliases that delegate to it.

**The one that catches people:** editing `.env` and running `restart` does
nothing, because a container keeps the environment it started with. Use
`./nora recreate`.

**Changing anything in `assets/` needs `./nora assets`, and the output gets
committed.** node runs in a throwaway container, so nothing is installed on the
machine you run it from; the Pi never builds and a fresh clone needs no network.

`./nora up` also generates a self-signed TLS cert on first run (idempotent
— see §4, "HTTPS via nginx"). The house serves on **https://<address>/home/**,
port 443, not `:8000` — nginx is the only published entry point. Your browser
warns once per device on first visit; see `docs/User/deployment.html`.

### First time on a new machine
```bash
git clone <repo> && cd nora-home
./nora up
```
`./nora up` creates `.env` from the example with a fresh secret key if it is missing.
`.env` is gitignored — secrets never enter the repo.

---

## 4. Decisions, and why

Read this section before changing architecture. Each of these was a real fork.

**The mockup is the UI reference, and it comes before the code (2026-08-09).**
`docs/Main_App/ui-overhaul-mockup.html` is a standalone, interactive prototype
of every surface — open it with a double click, no server, no build. **Any
future change to what a person sees goes into the mockup first, is shown, and
is approved before a line of production code is written.** That is now the
workflow, not a one-off for Phase 8.

It exists because a static picture could not settle the questions that actually
came up: whether a rearranged dashboard still tiles cleanly, whether the kiosk
scales past a handful of apps, whether text survives noon with rain. Those are
behavioural, and the prototype answers them in a browser in seconds.

**The harder lesson is what it took to make it trustworthy.** Four separate
times a list in it turned out to be invented rather than read — kiosk controls,
the widget catalogue, the Apps directory, and the nav groups. Each was fixed by
querying the running app (`manage.py shell` over the registry) or reading
`settings.py`, never by reasoning. **A mockup that shows plausible content is
worse than no mockup**, because it gets approved and then built. If you add a
screen to it, ground every list the same way and say in a comment where the
data came from.

**Follow the mockup exactly, every time — do not deviate from it (2026-08-10,
Story 55).** Stated plainly because it was not followed carefully enough once
already: Story 54 moved Alerts to the sidebar's Home group (right — the
mockup's `REGISTRY` puts it there) but left Measurements and Integrations
under Apps on the reasoning that the mockup "doesn't model them" — true of
`REGISTRY` alone, but the same mockup's `SYS_VIEWS` gives System four tabs
including both, missed because it sits in a different part of the file. A
label ("Tasks" vs. the mockup's "Board"), a kiosk key bank quietly narrowed to
five items instead of all seven sections, a "Home" nav link where the mockup
says "Dashboard," a missing Shuffle button, a Health tab showing different
content than the mockup's own — none of these were deliberate calls someone
signed off on. They were small, independent driftings, each individually
defensible ("this is arguably better engineering") and collectively a mockup
that had stopped being the reference. **When the real implementation and the
mockup disagree, the mockup is right, and the fix is to change the
implementation — not to decide the implementation's version is reasonable and
move on.** If a real constraint (Django is server-rendered, not a SPA; a
family app has more registered apps than the mockup's two-entry toy REGISTRY)
genuinely forces a difference, write down *why*, in the same style as Story
49's phone-tabs comment — a reasoned, visible adaptation, not a silent one.
The difference between the two is whether someone reading the code six months
from now can tell it was a decision rather than a drift.

**The front end is rewritten from the mockup, not migrated (2026-08-09).**
Phase 8 is greenfield. `static/nora_home/css/*` and `static/nora_home/js/*` are
deleted and rebuilt from `ui-overhaul-mockup.html`; templates keep their Django
logic and lose their markup. Nothing is preserved for compatibility.

Decided because the alternative is worse: retrofitting five surfaces' worth of
CSS onto a new token layer means carrying both systems at once, and the existing
sheets already contain rules whose reason nobody remembers. A rewrite from an
approved reference is smaller than a migration.

**What this knowingly breaks**, and where it is owned:

- **`tests/qa/*` selects by class** — `.todo-card`, `.kiosk-tile`, `.card` and
  friends all disappear. Those 226 checks are rewritten, not adapted (Story 55).
- **`nh-charts.js`'s house theme goes with it.** Widgets still return ECharts
  option dicts — that contract holds — but the theme applied to them is new.
- **Keep two things that are not styling**: `nora_home/ui/zoom.py` writing
  `style="zoom:"` onto `<html>`, and the `data-surface` / `data-daypart` /
  `data-weather` attributes the scene and ramp both read. Everything else in the
  static tree is disposable.

**Phase 8 — the UI overhaul, and what it overturns (2026-08-09).**
Thirteen stories, 43–55, designed against that mockup and approved at gate 1.
Four written decisions are reversed, deliberately:

- **§4's "no npm, no bundler, no framework" is withdrawn — and built (2026-08-09,
  Story 43).** Vite + Tailwind v4
  + Alpine, with node confined to a Docker build stage so the runtime image
  stays node-free. Offline survives (output is committed) and the Pi still does
  not build — but **an app author now needs node to change a style**, which was
  the load-bearing half of the original rule. Accepted knowingly.
- **Almanac's warm apricot becomes an arc-reactor cyan**, dark only. The light
  theme is deleted rather than rebuilt, which halves the contrast matrix.
- **Season and the landscape leave the scene.** Time of day and real weather
  only.
- **The wall stops being its own design.** It renders the desktop layout one
  ramp up, which deletes a whole story from the original plan.

Two IA decisions follow from one rule — *Home is the base app; everything else
is an app*: Status and the House log merge into a **System** page belonging to
Home, and the Apps directory is deleted in favour of a ⌘K palette. **The
platform/house distinction stays real in code and stops being visible**, which
is what this file already says of Todo: *Level is deliberately not the test.*

**Corrected 2026-08-10 (Story 54):** this used to also say "only the four
registered apps with `nav=True` are called apps," grouping Alerts alongside
Measurements and Integrations under "Apps" in the sidebar. Nobody had actually
checked that against the mockup. `ui-overhaul-mockup.html`'s own `REGISTRY`
puts `alerts` inside the `home` entry's own `sections` — next to Dashboard,
System, Settings — and "Apps" there is Todo alone. Alerts now groups under
Home to match. Measurements and Integrations stay under Apps: the mockup's
`REGISTRY` doesn't model either one, so there was nothing there to follow for
them, and inventing a placement would be the same mistake this correction
fixes. Found by actually asking "does the sidebar match the mockup," not by
re-deriving the rule from memory — see §4 on why every list here has to be
grounded in something read, not reasoned about.

**One thing in Phase 8 is not merely unbuilt but unsolved.** Story 51 wants the
24" powered down without taking the kiosk with it. §2 records that `xset dpms
force off` blanks both screens and that per-output `xrandr --off` proved
fragile; the shared blanking was confirmed with the user and accepted at the
time. `vcgencmd display_power 0 <display>` is the likely answer on a Pi 5, and
**it must be proven on the hardware before that button ships.**

**Story 45 split itself into two halves once the size of the second one became
clear (2026-08-09).** The story's own text ("this is where the old front end
is deleted") describes one continuous piece of work: build the eleven
components, then rewire every real template onto them, then delete
`nora-home.css`/`dashboard.css`/`todo.css`/etc. Doing all three in one sitting
means the house is unverifiable — and possibly broken — for however long that
takes, which is exactly the risk `docs/Main_App/testing.md`'s *built, unproven*
distinction exists to name. So it split:

- **Phase A (done): the component library itself, additive.** `nora_home/ui/
  templatetags/nh.py`, `templates/nh/*.html`, `assets/css/{tokens,components}.css`,
  `assets/js/nh-picker.js`, and `/home/styleguide/` rendering all eleven
  components in every state. Nothing real loads any of it yet — every existing
  page renders exactly as it did before this story, provably, because nothing
  about them changed. Built, deployed to the Pi, and checked in a browser
  there, same discipline as Stories 43 and 44.
- **Phase B (not started): rewiring every real template, then deleting the
  old files.** This is the part with the actual blast radius — every page in
  the house, all at once, is what "this is where the old front end is
  deleted" actually means. It gets its own pass, verified page by page rather
  than merged with Phase A's already-large diff.

**Two real bugs, both found only by opening the styleguide in a browser —
neither would have been caught by the fact that `manage.py check` and the
Python suite were green.**

- **Tailwind v4's `@theme` always namespaces what it emits.** A colour
  declared `--arc-500` inside `@theme` compiles to `--color-arc-500` — the
  prefix is not optional — so every hand-written rule in `components.css`
  reading plain `var(--arc-500)` (matching the mockup exactly, which never
  used Tailwind's `@theme` for these) silently got nothing. Every swatch, every
  status colour, every readout rendered fully transparent; only glows and
  borders (plain custom properties, never routed through `@theme`) stayed
  visible. Fixed by moving the colour and ink tokens out of `@theme` entirely,
  into a plain `@layer tokens { :root { --arc-500: ...; } }` block — exactly
  what the mockup already does, and correct anyway, since nothing here uses a
  Tailwind utility class like `bg-arc-500`. `@theme` now holds only
  `--font-sans`/`--font-mono`, which need no prefix (font is already their
  namespace) and which Tailwind's own base layer forces into the output
  regardless of whether anything else references them.
- **Alpine reserves a component method literally named `init`.** It auto-
  invokes one, with zero arguments, on top of whatever `x-init` on the element
  also calls — naming the Picker's own setup method `init` collided with that
  reserved hook, and the automatic zero-argument call is what threw `Cannot
  read properties of undefined (reading 'dataset')`, on every page using the
  Picker, the moment Alpine started. Renamed to `setup`, called explicitly via
  `x-init="setup($el)"`.

Both are now regression tests (`tests/test_ui.py::test_the_colour_tokens_are_not_routed_through_theme`,
`tests/test_nh_components.py::test_picker_js_never_names_a_method_init`), and
both are the same lesson twice: a green Python suite proves the *data* is
right, never that the *browser* agrees — which is the entire reason
`docs/Main_App/testing.md`'s browser-verification step exists as a separate,
non-skippable pass.

**The cross-layer collision audit the story asked for turned out to need a
narrower rule than "every class token", not a broader one.** The literal
instruction — match every token in a selector, not just the first, the way
the mockup's own audit script was fixed to do — was tried first and flagged
this codebase's *own ordinary CSS* as colliding with itself: `.btn` against
`.btn:hover` (a state variant), `.card` against `html[data-app] .card` (this
codebase's own extensively-documented `[data-surface]`/`[data-app]` override
convention), `.card` against `.nh-tile > .card` (a structural refinement).
None of those are the mockup's actual bug shape. `.who`/`.cap`/`.bar`/`.body`
were each a *bare*, fully unscoped selector — no ancestor, no pseudo-class, no
attribute condition — reused by accident across two unrelated `@layer` blocks.
`tests/test_nh_components.py::_subject_compounds` compares only that: bare,
ancestor-free, ".read.crit"-style compounds. Deliberate overrides don't have
to out-shout genuine accidents for the test to see.

**There is a second front end on a branch, and the Pi was running it
(2026-08-09).** Found by deploying Story 43: `git pull` on the Pi updated a
branch called **`ui-design-system`**, not `main`. It carries **17 commits** of an
earlier, compiled Tailwind design system — flat dark theme, a real sidebar, a
themed heatmap — and none of it is in `main`. Nothing in this file, the
dashboard or `progress.md` mentioned it existed.

**Phase 8 supersedes it**, and the Pi is on `main` now. But two things are worth
keeping rather than losing with the branch:

- **It reached the same conclusion Story 43 did, independently:** a build input
  is not a static asset. `collectstatic` walks everything under `static/`, and
  `ManifestStaticFilesStorage` rewrites `url()`/`@import` targets in every `.css`
  it finds — it read `@import "tailwindcss"` as a relative path, raised
  `MissingFileError` in the entrypoint *before Daphne starts*, and every service
  depending on `web` refused to come up. Sources live in `assets/` for that
  reason, in both attempts.
- **Deploying `main` regressed the wall.** The year heatmap renders as a white
  grid again — `14e7a6b` on that branch fixed it and `main` never had the fix.
  Cosmetic, and Story 45 rewrites that widget anyway, but it is visible on the
  24" until then. `git checkout ui-design-system && ./nora upgrade` puts the old
  look back if anyone wants it before Phase 8 lands.

**The lesson is not the branch, it is that nobody could have known.** Check what
branch the Pi is actually on before deploying, and do not assume `git pull`
there touches `main`.

**The front end is built, and the numbers say it is fine on the Pi
(2026-08-09).** Story 43 was written to prove the pipeline before anything is
designed on top of it, so it ships the *existing* UI through Vite and changes
not one pixel. Measured on the Pi itself, arm64, node in a container:

    npm ci        15s   (34 packages)
    vite build    1.75s (19 modules, 18 entries)

The fallback — building on a laptop and committing `dist/` — was never needed,
though that is what happens anyway: **the output is committed, and the Pi's
runtime image has no node in it.** node exists in one Docker build stage and in
`./nora assets`, which runs `node:22-slim` as a throwaway container so nothing
is ever installed on a host. A fresh clone with no network still boots.

**One entry per file the templates already load**, rather than a bundle. The
kiosk does not load `todo.css` today, and merging entries would have changed the
cascade on surfaces nobody is looking at — precisely the silent breakage this
story exists to rule out.

**Two traps, both of which rendered the house wrong rather than raising:**

- **`{% vite_asset %}` emits a `<script type="module">` for every entry,
  including CSS ones.** Vite treats a `.css` entry as an entry like any other,
  so all six stylesheets went out as module scripts, Chrome refused them on MIME
  type, and the house rendered as unstyled black text. A CSS entry goes through
  `{% vite_asset_url %}` inside a real `<link>`; a test now fails on the other
  form.
- **`django-vite` installs its own top-level `tests` package into
  site-packages** (their packaging bug). A *regular* package beats a *namespace*
  package regardless of `sys.path` order, so it shadowed this repo's `tests/`
  and every app-contract test died with `ModuleNotFoundError`. Fixed by giving
  `tests/` an `__init__.py`, which makes the whole class impossible rather than
  this one instance.

**Sources moved to `assets/`; `static/` now holds only what is generated or
vendored.** That is what makes Story 45's deletion of the old front end a single
directory rather than a hunt through a folder that also contains ECharts.

**The wall is a screen someone stands at, not a poster (2026-08-07).** Two
rules were written when the 24" was a passive ambient view, and both outlived
that. Worth knowing as a pair, because the next thing dating from the same
assumption will fail the same way.

**It hid the mouse pointer outright.** The wall is the real app now and gets
driven from its own sidebar, so that means aiming blind. It also hid
*inconsistently*: **`cursor` is inherited, and an inherited value loses to any
directly-declared one — including the browser's own `a:link { cursor:
pointer }`.** The pointer vanished over the body and reappeared over every
link. It is now hidden only while the mouse is *still*, and the rule needs
`body, body *` to beat those declarations rather than inherit past them.

**And it only counted as "the wall" on the first hop.** The wall iframes the
real app, so the app is fetched at its own ordinary URL and needs
`Sec-Fetch-Dest: iframe` plus a referer to be recognised. That referer names
the wall's shell exactly once — the moment the kiosk points it somewhere.
**Click a link on the 24" itself and the referer is the previous app page**, so
detection fell back to User-Agent and the wall rendered at laptop type scale
with its zoom dropped. Silently. Any same-origin iframed document now counts.

Same-origin is the boundary, and it is stateless on purpose: a cookie would
risk a laptop that once visited the wall's URL getting stuck wall-sized. It
assumes **nothing in this house iframes an app page except the wall** — true
today, and the thing to check before adding a second iframe.

**The lesson is the detection, not the pointer.** A wall silently rendering at
laptop scale announces itself in no other way — this is the second such bug
after `--nav-width: 244px`, and both were invisible to the suite and obvious on
the glass. The pointer is the one wall behaviour that is not a *size*, which is
the only reason a human noticed this one at all.

**The base app shows the weather; a house app shows the work (2026-08-07).**
Two surfaces, two jobs, and conflating them was making apps unreadable.

The living background — real season, time of day, weather — is the whole
"charm outside, polish inside" idea, and it is *the point* on the base app's
pages. **Inside a house app it is not.** Somebody who opened Todo came to read a
board; at the house's 0.3 pane opacity the columns and cards washed out against
a bright afternoon, and the priority columns had no pane at all — four headings
floating on blue with nothing to say where one ended and the next began.

So `data-app` on `<html>` (set from the URL by `nora_home.ui.context_processors`)
drives near-opaque panes for every app, and the scene stays visible but settles
behind. **An app gets this without styling itself**, which matters more than the
look: a family member's agent should not have to know about `--pane-rgb` to
produce something readable.

**Which pages count as "an app" is the subtle part**, and `app_for_path()`
carries it: *anything under `/home/` is the base platform*, including the
several platform pages that are separate Django apps internally (notifications
at `/home/alerts/`, telemetry at `/home/measurements/`). Nobody went "into" an
app by opening Alerts. **Level is deliberately not the test** either — Todo is
Level 2 and `is_platform`, but it is an app in every way a person cares about.

**The same request settled navigation.** The sidebar showed the house's pages no
matter where you were, so an app's own sub-pages had no route to them at all —
Todo's calendar, reporting and labels were reachable only by typing a URL, and
it shipped that way. Apps now declare `nora_sections` and the sidebar leads with
them. The house nav stays *underneath* rather than being replaced: navigation
must never become a dead end, and "back to the house" should not be something
each app has to remember to build.

**Screen size is a setting, because only the person in front of the screen can
judge it (2026-08-07).** Settled after three wrong answers, and the reasoning is
worth not repeating.

**What no browser can know is viewing distance.** A CSS pixel is already a
*reference pixel* — the visual angle of one pixel on a 96dpi screen at arm's
length — and `devicePixelRatio` normalises for physical size, which is why a
460ppi phone reports ~390 CSS px. So a site gets physical-size normalisation
free, for the one distance the web assumes. The 24" wall and a laptop both
report 1920×1080; nothing in CSS distinguishes them. `data-surface="wall"`
carries that missing fact.

**Scaling the root font-size is the wrong mechanism** — tried at 160%, then
135%, then a clamped `vw`, and reported as "zoomed in" every time. It grows every
`rem` while borders, shadows and corner radii stay 1-device-pixel hairlines, so
the proportions come apart even when the text size is right.

**`--force-device-scale-factor` is the right mechanism and the wrong layer.**
It is what TV and signage platforms use, and it works — but a launch flag can
only be changed by regenerating `~/.nora/start-*.sh` and restarting Chromium,
which means an SSH session. A number a family member is expected to tune has to
live where they can reach it.

**So: CSS `zoom`, stored in `HouseSetting`, edited in Settings → Screens**
(`nora_home/ui/zoom.py`). It was measured against the flag on the Pi's own
Chromium before being chosen, because "zoom scales everything" had to be a fact:

    a 100px box with 10px borders   plain 120px  ->  zoom 1.25  150px
    html { zoom: 1.25 } on 1920     documentElement.clientWidth   1536

Both match `--force-device-scale-factor=1.25` exactly. Both screens now launch
at scale 1 so the two cannot multiply. **Only the wall and the kiosk are
offered** — a phone or laptop is held at arm's length, which is what every
browser default already assumes, so `nh_zoom` is `None` there and no attribute
is emitted at all.

**One measured difference from the flag:** media queries still evaluate against
the *unzoomed* viewport. Immaterial on the wall (breakpoints are 860px and
620px), but at 1024 physical the kiosk could put its layout viewport under 860
while media queries still said 1024 — which is why the kiosk's ceiling is lower
than the wall's.

**The scaling only works because everything else is `rem`.** That has broken
twice, both times found by looking at the screen and never by a test: Gridstack's
`cellHeight: 80`, then `--nav-width: 244px` clipping "Measurements" — the second
*after* the first had been found and written up. Fixing the instance is not
fixing the class. `tests/test_ui.py` guards the tokens and asserts the scale has
not crept back into CSS.

**Changing a launch flag needs `./nora screens relaunch`.** The scripts in
`~/.nora/` are generated, so a deploy, a reload and even a reboot leave the old
flags in place. That caught this project twice before the command existed.

**Editing an applied migration, once, to delete an app (2026-08-06).****Editing an applied migration, once, to delete an app (2026-08-06).**
CLAUDE.md §6 says never edit an applied migration. Story 40 had to, and the
reasoning is worth not re-deriving. `Task.escalation_policy` pointed at
`tracker.EscalationPolicy`, and both of Todo's earlier migrations declared a
dependency on `('tracker', '0001_initial')`. **A migration naming a node no
installed app can supply does not degrade** — Django refuses to build the graph
and every management command dies with `NodeNotFoundError`, so there is no
version of deleting the app that leaves those dependencies in place.

The rule's *purpose* — that replaying history produces the same schema — is
preserved rather than waived: `EscalationPolicy`'s `CreateModel` block was
copied verbatim out of the deleted `tracker/0001_initial` into `todo/0001`, so a
fresh database gets byte-for-byte the table the tracker used to create.
`todo/0007` exists only for databases where the *original* ran, and is a no-op
on any built since.

**The trick in 0007 is worth reusing.** It converges with a single `RENAME
TABLE` rather than create-copy-repoint-drop. Renaming carries the rows, their
primary keys and their indexes across, and on both MySQL and SQLite it rewrites
the foreign keys in *referencing* tables to follow the new name — so
`todo_task`'s constraint followed the table without anyone dropping and
recreating it. That is the step that would otherwise have needed vendor-specific
SQL plus a lookup of MySQL's auto-generated constraint name. The only residue is
cosmetic: carried-over constraint names still read `..._fk_tracker_e`, and
Django looks constraints up by the columns they cover, never by name.

**And it was rehearsed, not reasoned about.** The live schema (no data) plus its
`django_migrations` rows were dumped into a throwaway `nora_rehearsal` database
and migrated there first, then checked for all four things that could have gone
wrong — rows carried with their pks, FK repointed, tracker tables gone,
`migrate --check` clean — before the real database was touched. For a migration
that cannot be undone, on the one database that matters, that rehearsal cost ten
minutes and is the reason this section is short.

**Levels replace "the platform never depends on a house app" (2026-08-05).**
That rule was withdrawn once Todo needed to become something the base platform
itself relies on for scheduling, reminders and escalation — a house app can be
uninstalled at any moment, so nothing the base needs could ever safely live
there. Levels give a third option: **1** is the base (`nora_home/*` apps that
never depend on anything below), **2** is an app the base deliberately leans on
and the house degrades without (Todo), **3** is a family app under `houseapps/`
(the default — uninstall freely, nothing breaks). The one rule Levels actually
enforce: nothing at Level 1 or 2 may import a Level 3 app —
`tests/test_house_apps.py::test_level_1_or_2_never_imports_a_level_3_app` checks
this over every registered app, not only house apps. `nora_level` lives on
`NoraAppConfig` (`nora_home/core/registry.py`), defaulting to 3. Full writeup:
[`docs/Main_App/subsystems/todo.md`](docs/Main_App/subsystems/todo.md) §1.

**`.env` was tracked in git for two days, and it cost a session (2026-08-05).**
Commit `a173dcf` added `.env` to the repo and deleted the `.env` line from
`.gitignore`. The committed copy carried `.env.example`'s **laptop** defaults, so
**every `git pull` on the Pi silently replaced the house's real configuration** —
`config.settings.pi` → `dev`, MySQL → SQLite, `America/New_York` →
`America/Los_Angeles`, `DEBUG=0` → `1`, ports 443/80 → 8443/8080, and the real
Slack and MCP tokens → empty. It happened twice in one session before anyone
understood why.

**Fixed the same day**: `.env` and a leftover `.env.check_tmp` are untracked, and
`.gitignore` now carries `.env` / `.env.*` with `!.env.example`, so the whole
class is covered rather than just the one file. The repo is private, and the
values that were briefly committed are staying as they are — a deliberate call,
not an oversight.

**Keep the diagnosis, because the failure mode will recur in other forms.** It
presents as total data loss and is not. Swapping `.env` changes nothing until a
container is recreated, and then *that* container comes up on a fresh, empty
SQLite database in its own writable layer — **there is still no volume for
`db.sqlite3`**, so a house running on `dev` settings has no persistence at all.
Containers that were not recreated keep running on MySQL with every row intact,
because a container keeps the environment it started with. That same fact is the
recovery: a still-running container is the best available record of the correct
configuration.

```bash
# what is this container ACTUALLY connected to? ask before concluding anything
docker compose exec -T web python manage.py shell -c "
from django.conf import settings; print(settings.DATABASES['default'])"

# rebuild .env from a container that has NOT been recreated, then apply it
docker inspect nora-home-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}'
./nora recreate
```

**Django over FastAPI/Node.** The admin alone is worth it: a family member can edit
an escalation policy or retime a job without a deploy. Batteries-included matters
more than raw speed on a home LAN.

**MySQL for relational, Mongo for documents, both.** Anything Todo joins
across lives in MySQL. Journals, AI transcripts, and raw integration payloads go to
Mongo where the shape can change without a migration. Mongo is *optional* — the house
runs degraded, not broken, without it.

**RabbitMQ as the Celery broker, Redis for everything else.** RabbitMQ gives durable
queues and real routing so a runaway app task cannot delay an escalation. Redis is
cache + channel layer + rate limits. `NORA_HOME_BROKER_USE_REDIS=1` collapses this to
Redis-only for laptop work.

**Occurrences are materialized, not computed.** Todo writes concrete `Instance`
rows ahead of time over a 90-day horizon (the tracker did the same two weeks
ahead before Story 40 replaced it). That is what makes "what did I miss last
March" answerable and gives escalation state somewhere to live.

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

**Apache ECharts + Gridstack.js, vendored, no build step of their own.** ECharts
because it handles the whole range from sparkline to heatmap, themes cleanly, and
renders acceptably on a Pi. Gridstack for the draggable home grid. Both are
vendored into `static/nora_home/vendor/` rather than pulled from a CDN, because
the house must work with the internet down, and neither needs npm to use.

This is narrower than it used to read. §4's Phase 8 entry withdrew the
project-wide "no npm, no bundler, no framework" rule for the app's *own*
CSS/JS — that now goes through Vite (`assets/` → committed `static/…/dist/`,
node confined to a Docker build stage the Pi's runtime image never sees). What
holds here is just ECharts and Gridstack specifically staying vendored,
pre-built, dependency-free files — not a platform-wide stance any more.

**A widget ships at every size it declares, including the phone.** Size
variants (S/M/L/XL) are part of the widget contract from Phase 8, and each is a
*designed* state rather than the same content stretched. A test renders every
widget at every size it declares, on every surface, and fails on overflow —
because this failure is silent. The mockup showed the shape of it: a phone
stacks cards in a flex column, flex items shrink by default, and a card pinned
to a fixed height centres its overflow, so a chart appeared to sit on top of its
own title with nothing logged. Anything sized by its container on desktop —
charts, rings, heatmaps — needs a floor on the phone, and some widgets need a
different presentation there rather than a smaller one: a month grid gives each
day ~48px on a 390px screen, which cannot hold a task title, so the phone shows
priority dots plus a list.

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

**Design system: "Almanac" — a living, seasonal background, not a themed
dashboard.** Two rounds of dashboard-shaped mockups (kept in `docs/design-options.html` until it was deleted 2026-08-03)
were rejected as generic — recognizable as "an AI-generated dashboard" no
matter the palette, because a sidebar-plus-card-grid is that template
regardless of colour. The direction that stuck instead: the actual season,
time of day, and real outside weather are composited as a living background
*behind* the real, fully-functional app — never replacing it, never becoming
an ambient/passive screen (that idea was explicitly tried and rejected too).
"Charm outside, polish inside": the atmosphere (sky gradient, horizon,
sun/moon, rain/snow/clouds) carries the personality; the data sitting on top,
in translucent glass panes, stays disciplined — tabular numbers, no
ornamentation. Landed as `nora_home/ui/scene.py` (season from date + house
latitude; day/night from *real* sunrise/sunset, not fixed clock hours),
a first concrete integration (`nora_home/integrations/providers/weather.py`,
Open-Meteo, no API key — just `NORA_HOME_LAT`/`NORA_HOME_LON`), and
`static/nora_home/css/nh-scene.css` retrofitting `.card`/`.sidebar`/
`.kiosk-tile` onto it. Both screens (the wall, via the app it iframes; the
kiosk, directly) poll the same `core:weather_current` endpoint every 5
minutes so they can't drift onto different "moments." See §2's "not done"
note above — the engine is real and live-tested against the real API, but a
full per-component restyle across all five surfaces is not done.
**2026-08-03**: the topbar's profile icon (`.profile-trigger`) now carries
the sun/moon itself — its background picks up the same daypart gradient as
`.nh-scene__orb` — so the ambient orb is hidden wherever that icon exists
(`nh-scene.css`, scoped by `data-surface`), leaving it only on the kiosk,
the one template with no topbar at all to carry it instead.

**HTTPS via nginx, self-signed, nginx-only.** Asked directly, and answered
directly: this house has no public domain — it's a Pi on the LAN — so no
certificate authority could ever issue it a certificate a browser trusts by
default. Chose a self-signed cert (`scripts/gen-self-signed-cert.sh`) over
standing up a private CA (`mkcert`, trusted per-device) or acquiring a real
domain for Let's Encrypt, and chose to make nginx (`nginx/nginx.conf`) the
*only* published entry point rather than leaving `:8000` open alongside
`:443` for debugging — both were explicit choices, not defaults, made when
asked. `web` no longer publishes a host port at all; Daphne is reachable only
through nginx, internally, over the Docker network. **The one real trap this
surfaced**: `prod.py` turns HSTS on for a year whenever `SECURE_SSL_REDIRECT`
is true — correct for a CA-issued cert, actively dangerous for a self-signed
one, since Chrome and Firefox both withdraw the certificate-bypass
click-through entirely on an HSTS-pinned host. The first cert rotation (or
the Pi's LAN IP changing, which the cert's SAN is keyed to at generation
time) would have permanently locked every laptop and phone out with no way
back in short of clearing HSTS state by hand on every device. `pi.py` now
forces `SECURE_HSTS_SECONDS = 0` regardless, with the reasoning written down
so it doesn't get "helpfully" re-enabled later. Verified locally via Docker
Compose against real `config.settings.pi` settings, then on the physical Pi
itself the same session — see §2's "Verified on the Pi (2026-08-03)" note.

---

## 5. Web app vs native kiosk app — answered

**Build it as a web app served locally, displayed full-screen by Chromium in kiosk
mode, and installable as a PWA on phones.** That is what `scripts/lib/provision-pi.sh`
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
(`nora_home.todo.api`, `nora_home.notifications.api`, `nora_home.telemetry.api`) or send a signal
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
  todo/            tasks, instances, recurrence, reminders, escalation, alarms
  ai/              Claude client, model tiers, cost accounting
  mcpserver/       MCP tool registry, stdio server, HTTP transport
  datastores/      mongo, object storage, backup/restore commands
  displays/        wall + kiosk models, bus, consumers
  telemetry/       series, readings, rollups, thresholds
  integrations/    integration framework, scheduling, failure handling
  ui/              surface detection, Nora bot, theme, the nh_* component
                   library (ui/templatetags/nh.py — Story 45)
houseapps/         family apps live here (empty until Story 24)
templates/         platform templates
  nh/              the component library's own partials (Story 45) —
                   card.html, stat.html, list.html, picker.html, ...
assets/            the front end's SOURCE — css/, js/. Vite's input; the old
                   half (nora-home.css, dashboard.css, todo.css, ...) is
                   deleted once every real template is rewired onto
                   tokens.css/components.css — see CLAUDE.md §4, Story 45
static/nora_home/       dist/ (Vite's committed output), vendor/, audio/
package.json       front-end deps. node is build-time only, never on a host
vite.config.js     one entry per file the templates load; output is committed
docker/            entrypoint
nora               the runner — install, up, upgrade, backup, apps, screens
scripts/           run-tests.sh, gen-self-signed-cert.sh, vendor.sh
  lib/             provision-pi.sh, pre-provision-pi.sh
docs/
  User/            deployment.html, dashboard/ — for people, not agents
  Main_App/        DEVELOPMENT, cross-functionality, architecture, testing,
                   progress, and subsystems/ — one file per platform subsystem
  House_Apps/      one folder per family app, holding that app's docs
```

---

## 8. Progress log

This used to hold entries directly. It stopped on 2026-07-31, the same day
`docs/Main_App/progress.md` was created as the dedicated history file — every
session since has appended there instead, per §0's own table. Both the
original three entries here and everything since now live at
[`docs/Main_App/progress.md`](docs/Main_App/progress.md), which is the only
place new entries go. Kept as a heading, not deleted outright, so nothing
that ever linked to `CLAUDE.md#8-progress-log` breaks.

---

## 9. Open questions for the user

Ask before assuming.

1. **Which design direction?** Blocking any real UI work (Story 23). See
   `docs/design-options.html` (since deleted) — the second, visualization-led set. The first set was
   rejected for looking like a todo app.
2. **Slack: bot token or webhook?** A bot token gives DMs and threading, which the
   escalation ladder is designed around. A webhook is one channel and zero setup.
   The code supports both; the token path is better.
3. **Which app first?** The skeleton needs one real app to prove itself. House
   maintenance is the best candidate — it exercises long cadences, escalation, and
   the wall display without needing anyone's health data.
4. **Repo hosting and remote?** `scripts/lib/provision-pi.sh` needs `NORA_HOME_REPO` set.
