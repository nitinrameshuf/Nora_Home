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
| A story's status, or added one | [`docs/User/dashboard/nora_home_dashboard.html`](docs/User/dashboard/nora_home_dashboard.html) — the `STORIES` object, the summary counts, and the phase bars |
| Anything at all, in a working session | [`docs/Main_App/progress.md`](docs/Main_App/progress.md) — a dated entry, newest at the bottom |
| A component, boundary, or data flow | [`docs/Main_App/architecture.md`](docs/Main_App/architecture.md) — including the Mermaid diagrams |
| One subsystem's models, API, tasks, or gaps | The matching file in [`docs/Main_App/subsystems/`](docs/Main_App/subsystems/) |
| A published cross-app function | [`docs/Main_App/cross-functionality.md`](docs/Main_App/cross-functionality.md) — signatures are copied from the code, so keep them true |
| The app contract, or anything about the five surfaces | [`docs/Main_App/DEVELOPMENT.md`](docs/Main_App/DEVELOPMENT.md) |
| Anything at all — add or update a test | `tests/test_<subsystem>.py`, and a house app's own `tests/test_<app>.py` |
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
  screen (all five documented buttons now exist). 11 of 15 Phase 7 stories
  built (28–37 and 40, plus 42 out of number order — see its own warning), including
  Slack in both directions: reminders arrive as DMs with Done/Skip/Snooze/
  Reassign buttons, and `/todo` answers back over Socket Mode. **Full
  design, decision log, and per-story "as built" notes**:
  [`docs/Main_App/subsystems/todo.md`](docs/Main_App/subsystems/todo.md).
  Build order and what's left: [`docs/Main_App/subsystems/todo-build-brief.md`](docs/Main_App/subsystems/todo-build-brief.md).
  Story-by-story status: the dashboard. **Stories 35 and 36 have run on the Pi
  against MySQL** — Reporting, settings and the system board all rendered
  there, the priority-mix query and the system-task dedupe both checked against
  MySQL specifically, and each seen on the physical wall and kiosk through the
  kiosk's own navigation. Stories 28–34 and 42 have still only run against
  SQLite on a laptop. **Story 40 (Tracker Removal & House Log) is unblocked**
  — its only dependencies were 35 and 36.
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

### Not done — pick up here
0. **Phase 7 — Todo, 14 of 15 (93%). Two pieces left:** **Story 24** (house
   maintenance, the first real family app, unblocked since Story 27) is what
   actually proves the platform was worth building rather than another platform
   story — and **its `requirements.md` needs your approval before any code**,
   the first of DEVELOPMENT.md's three gates; **Story 41** (Tests, Docs &
   Deploy, Sonnet, ~6h) is now unblocked and is volume rather than difficulty.
   Stories 28–40 built and green (**884 tests**), plus Story 42 (Shared Tasks &
   Approval, built out of number order — see its own entry for why). Read
   [`docs/Main_App/subsystems/todo.md`](docs/Main_App/subsystems/todo.md)
   before touching this app — it is the approved design and the record of every
   decision made building it; do not re-derive anything already settled there.
   [`docs/Main_App/subsystems/todo-build-brief.md`](docs/Main_App/subsystems/todo-build-brief.md)
   has the remaining phases in build order. **Three things a fresh session needs
   to know before doing anything else:**
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
4. **Tests: 891, one file per subsystem, green.** `./scripts/run-tests.sh` (or
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
   **`./nora qa`** is the second layer: 106 checks driving a real Chromium
   against the running house — every page rendered and checked for console
   errors, the journeys clicked through, both screens open at once so a kiosk tap
   can be seen moving the wall, and contrast measured from pixels. ~4 minutes,
   run from a laptop, deliberately separate from the fast suite. It found two
   real bugs on its first run — a checkbox with no accessible name, and the
   light theme unreadable at dusk (2.06:1); **both fixed** — plus one about the
   tools: axe's colour-contrast rule is unusable against `backdrop-filter` over a
   living gradient, and believing it would have meant degrading readable text.
   Contrast is measured from pixels instead.
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

**The wall's type scale can only ever be half-automatic (2026-08-06).**
Asked directly — "should that not scale automatically by display size?" — and
the answer is worth keeping, because the intuition is right and the limit is
not obvious. What decides how big text needs to be is its **angular** size:
physical height over viewing distance. CSS can measure neither. It cannot ask
how many inches the panel is, and it certainly cannot ask how far away somebody
is standing — **the 24" wall and a laptop both report 1920×1080**. A rule driven
by viewport alone would therefore render the laptop at wall size.

That is what `data-surface` is actually for. Declaring the wall server-side is
not a statement about pixels, it is a statement about **~3 metres**, and that is
the one input no media query can supply. Surface detection is not a workaround
for missing CSS features; it carries information the browser does not have.

Given the distance, viewport fraction is the best available proxy for physical
size, so the wall's root is `clamp(18px, 1.125vw, 28px)` rather than a fixed
percentage — type becomes a constant *share of the screen*, so the same physical
panel stays right if it is ever driven at a different resolution, and the clamp
stops an odd display going unreadable in either direction. **Known limit:** a
different-sized panel at the same distance is still wrong, and `vw` slightly
over-corrects there (a 32" would get physically larger text when it should get
the same). Changing the panel, rather than its resolution, means revisiting it.

**And the thing that makes all of it work is fragile in a specific way.** One
root declaration scales everything *only* while every other size is `rem`. That
has now broken twice, both times found by looking at the physical screen and
never by a test: Gridstack's `cellHeight: 80` clipped the stat tiles, and
`--nav-width: 244px` clipped "Measurements" in the sidebar — the second one
after the first had already been found, written up, and filed as a lesson. Fixing
the instance is not fixing the class. `tests/test_ui.py` now reads the stylesheet
as text and asserts the tokens are `rem`; it cannot see a browser layout, so it
guards the known tokens and nothing else. **If you add a fixed pixel size to
anything that holds text, you are adding the third instance.**

**Editing an applied migration, once, to delete an app (2026-08-06).**
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
  ui/              surface detection, Nora bot, theme
houseapps/         family apps live here (empty until Story 24)
templates/         platform templates
static/nora_home/       css, js, vendor
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

Append here. Newest last. Keep entries short and factual.

### 2026-07-31 — skeleton written and booted
- Platform apps, registry, tracker (deleted 2026-08-06), escalation, notifications, AI, MCP, datastores,
  displays, telemetry, integrations, dashboard.
- Docker Compose stack, Makefile, Pi install script, `install_app` command.
- URLs restructured: platform under `/home`, house apps at the root (`/habits/`).
- Home screen is now a per-person grid of widgets from any app, with ECharts and
  Gridstack vendored for offline use.
- Migrations generated and applied; ran end to end on SQLite.
- Four design directions rendered in `docs/design-options.html` (since deleted) — awaiting a choice.

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
  `docs/Main_App/progress.md` for the full table of what moved.
- `docs/` established with a story dashboard (same shape as the robot project's),
  architecture diagrams, and a progress log. Documentation duty written into §0.
- First set of design directions rejected as too task-list-focused; a second,
  visualization-led set produced for review.

### 2026-07-31 — the third-party app-building path, actually tried
Asked "is this ready to hand to others to build apps inside it?" — rather than
answer from the code, actually played a new house-app author: cloned fresh,
followed `docs/Main_App/DEVELOPMENT.md`'s "Ten-minute start" literally, and hit two real bugs
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
  templates live in a directory named after the old app. `docs/Main_App/DEVELOPMENT.md`'s
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
   `docs/design-options.html` (since deleted) — the second, visualization-led set. The first set was
   rejected for looking like a todo app.
2. **Slack: bot token or webhook?** A bot token gives DMs and threading, which the
   escalation ladder is designed around. A webhook is one channel and zero setup.
   The code supports both; the token path is better.
3. **Which app first?** The skeleton needs one real app to prove itself. House
   maintenance is the best candidate — it exercises long cadences, escalation, and
   the wall display without needing anyone's health data.
4. **Repo hosting and remote?** `scripts/lib/provision-pi.sh` needs `NORA_HOME_REPO` set.
