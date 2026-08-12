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
- [`docs/Main_App/found-by-the-user.md`](docs/Main_App/found-by-the-user.md) —
  every bug, invented rule and over-claim **the user caught rather than an
  agent**. Read it before trusting your own review of your own work.
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
- **HDMI-0 → 24" 1080p display**, always on, wall-mounted, desk viewing distance.
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
  kiosk's own navigation. Stories 28-34, 41 and 42 are marked Complete on the
  dashboard as of 2026-08-08. **Story 41 (Tests, Docs & Deploy) closed the phase**:
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

### Verified on the hardware

Everything below has been *seen working* on the Pi, not just reviewed. The
narrative of how each was found lives in
[`docs/Main_App/progress.md`](docs/Main_App/progress.md); only the standing
facts are here.

- **The stack runs on real hardware** against MySQL, Mongo, RabbitMQ and MinIO.
  All nine services healthy; migrations and `bootstrap_home` run on container
  start.
- **Both screens render on their own physical monitors** in Chromium kiosk mode.
  This needs the **X11 session, not Wayland** — `labwc` refuses to place a
  fullscreen window on a chosen output, so both instances landed on the same
  screen. `provision-pi.sh` §6 makes the switch itself. Side effect: Pi Connect's
  screen-share only works on Wayland, so it stops working; SSH is unaffected.
- **The kiosk drives the wall.** Tapping an app tile navigates the wall's iframe
  and swaps the kiosk to that app's own controls; back returns without
  disturbing the wall.
- **Touch is mapped to the kiosk's own output** via an X11
  `TransformationMatrix` (`provision-pi.sh` §8) — X11 has no automatic
  per-output touch mapping, so without it touch scales across the whole desktop.
- **HTTPS on :443 via nginx**, self-signed. Daphne's `:8000` is not published.
- **Chromium launches with `--password-store=basic`** — a fresh profile
  otherwise reaches for the OS keyring, which auto-login never unlocks, and the
  prompt blocks unattended boot.
- **The house speaks.** Groq synthesises, `SoundChannel` writes a WAV to the
  bind mount, a host timer plays it. Reminders arrive in Slack as DMs with
  working Done/Skip buttons.
- **The design system is live on both screens** (2026-08-08), with 943 tests
  green.

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
     system-task dedupe, and all seen on the physical wall and kiosk). Stories 28-34, 41 and 42 were marked
     Complete on 2026-08-08.
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
1. **Design system.** The house builds its stylesheet with **Tailwind v4**,
   compiled in the Dockerfile's `css` stage (Node lives there only; the runtime image
   never sees npm). Source is `assets/css/nora.css` — **not** under `static/`,
   because `collectstatic` rewrites `@import` in anything it walks and takes
   the web container down on boot. Output is `static/nora_home/css/nh.css`,
   gitignored, linked last in `base.html` *after* `{% block head %}`.

   Components are named for the classes the templates already use (`.card`,
   `.btn`, `.nav-link`, `.todo-col`), so one sheet restyles 30 templates
   without rewriting their markup. Six fluid `clamp()` type roles replace three
   hard-coded per-surface scales; one 4px spacing rhythm replaces eleven ad-hoc
   values; three solid surface levels replace translucent panes over a moving
   gradient. **940 tests green, deployed and screenshotted on the Pi.**

   The old hand-written sheets still load underneath and still style anything
   the new one has not reached. **They are meant to be deleted**, and until they
   are, the component layer has to stay *unlayered* to beat them — see §4.

   The living background is hidden in the app chrome. `nh-scene.css`,
   `nora_home/ui/scene.py` and the Open-Meteo integration remain, for the
   kiosk's idle screen. Verified locally (real fetch
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
2. **Tests: 943, one file per subsystem, green.** `./scripts/run-tests.sh` (or
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
3. **PWA manifest and service worker** — not written.
4. **No favicon** — the logs show steady `/favicon.ico` 404s.

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
`./nora up` also generates a self-signed TLS cert on first run (idempotent
— see §4, "HTTPS via nginx"). The house serves on **https://<address>/home/**,
port 443, not `:8000` — nginx is the only published entry point. Your browser
warns once per device on first visit; see `docs/User/deployment.html`.

### First time on a new machine
```bash
git clone <repo> && cd nora-home
./nora up
```
`./nora up` creates `.env` from the example with a fresh secret key if missing.

---

## 4. Decisions, and why

Read this section before changing architecture. Each of these was a real fork.

**Tailwind, and the rules nobody agreed to (2026-08-08).** Asked why the UI
looked unprofessional, the honest answer turned out to be measurable rather
than aesthetic. Across 2,615 lines of CSS: `clamp()` appeared **once**,
`@container` **never**, `dvh` **never** (five uses of `100vh`, which hides a
row under the iOS URL bar), 128 hard-coded pixel values, and the type scale
hard-coded **three times** and chosen server-side from a User-Agent regex. A
13" laptop and a 32" monitor rendered byte-identical type. The zoom slider in
Settings → Screens existed because the layout could not respond on its own.

**The 24" is a monitor.** It was never asked to be read from three metres —
that was in §1 as fact, and it is what justified a wall type scale, a fifth
surface, and CSS `zoom` stored in `HouseSetting`. Removing the claim removes
all of it.

**RabbitMQ stays, and the real bug was the worker.** Proposed removing it;
that was too quick. Five queues are genuinely in use — but one worker consumes
all five on three slots, so a runaway app task *can* delay an escalation,
which is the exact thing the broker was chosen to prevent. `task_acks_late` was
never switched on either, so a task in flight when a worker dies is lost today.
The fix is two workers (`platform,alerts` apart from `apps,ai,integrations`),
not a different broker. **Not done yet.**

**Three cascade traps, in order, each of which made a deploy look like a
no-op.** Worth knowing as a set, because each one hid the next:

1. **Unlayered beats layered, whatever the specificity.** The new components
   sat in `@layer components`; every old sheet is unlayered. Layered
   `.btn-primary` lost to unlayered `.btn-primary` — same selector — because
   the cascade compares layers *before* it looks at specificity.
2. **`{% block head %}` comes after the base `<link>`s.** `todo.css` and
   `dashboard.css` are injected there, so a sheet linked above the block loads
   *earlier* and loses. The design system now links after the block.
3. **`wall_live.html` and `kiosk.html` do not extend `base.html`.** They needed
   the stylesheet added by hand, which is why both physical screens sat
   unchanged while every other page had moved on.

**And the thing no stylesheet could have fixed: the ragged dashboard was
data.** Stored layouts held tiles at `h=2,3,4,5` with gaps at `x=3,5,7,9`, so
the cards genuinely were different heights. Every widget class already declared
a `default_size` and nothing had ever reconciled the two. `manage.py
tidy_dashboards` repacks onto the declared sizes and equalises each band. It is
**not** automatic — `items` is a person's own arrangement.

**The wall is a screen someone stands at, not a poster (2026-08-07).** Two
rules dated from when the 24" was a passive ambient view.

**The pointer was hidden outright**, so driving the wall from its own sidebar
meant aiming blind — and it hid *inconsistently*, because `cursor` is inherited
and an inherited value loses to any directly-declared one, including the
browser's own `a:link { cursor: pointer }`. It vanished over the body and
reappeared over every link. Now hidden only while the mouse is still, and the
rule needs `body, body *` to beat those declarations rather than inherit past
them.

**And it only counted as "the wall" on the first hop.** The wall iframes the
real app, so detection needs `Sec-Fetch-Dest: iframe` plus a referer naming the
wall's shell — which is true exactly once, when the kiosk points it somewhere.
Click a link on the 24" itself and the referer is the previous app page, so
detection fell back to User-Agent, silently. Any same-origin iframed document
now counts. Same-origin is the boundary and it is stateless on purpose: a cookie
would risk a laptop that once visited the wall's URL getting stuck wall-sized.
It assumes **nothing in this house iframes an app page except the wall** — check
that before adding a second iframe.

**A house app leads its own navigation (2026-08-07).** The sidebar showed the
house's pages wherever you were, so an app's sub-pages had no route to them at
all — Todo's calendar, reporting and labels were reachable only by typing a URL,
and it shipped that way. Apps declare `nora_sections` and the sidebar leads with
them; the house nav stays *underneath* rather than being replaced, because
navigation must never become a dead end.

`data-app` on `<html>` (from `nora_home.ui.context_processors`) marks app pages.
**Which pages count is the subtle part**, and `app_for_path()` carries it:
*anything under `/home/` is the base platform*, including platform pages that
are separate Django apps internally (notifications at `/home/alerts/`, telemetry
at `/home/measurements/`) — nobody went "into" an app by opening Alerts. Level
is deliberately not the test either: Todo is Level 2 and `is_platform`, but it
is an app in every way a person cares about.

**Screen scaling.** A per-screen scale
was built (CSS `zoom` in `HouseSetting`, Settings → Screens) on the assumption
the 24" was read from three metres. It is not, so fluid `clamp()` type covers
phone through 4K and `nora_home/ui/zoom.py` now serves the 10.1" kiosk alone.
Two measured facts survive the change:

- **`zoom` scales borders, shadows and radii; a root font-size multiplier does
  not.** Growing every `rem` while hairlines stay 1 device pixel is what reads
  as "zoomed in" even when the text size is right. Measured against
  `--force-device-scale-factor` on the Pi's own Chromium: both give a 100px box
  with 10px borders an identical 150px at 1.25.
- **Media queries evaluate against the *unzoomed* viewport.** At 1024 physical
  the kiosk can put its layout viewport under a 860px breakpoint while media
  queries still report 1024 — which is why the kiosk's zoom ceiling is lower
  than the wall's ever was.

**Editing an applied migration, once, to delete an app (2026-08-06).**
CLAUDE.md §5 says never edit an applied migration. Story 40 had to, and the
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
(the default — uninstall freely, nothing breaks). `nora_level` lives on
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

**Apps mount at the URL root** — `/workout`, `/family`, `/maintenance`. The platform
lives under `/home`. `RESERVED_SLUGS` in `nora/core/registry.py` stops an app
claiming a platform prefix.

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

## 5. Conventions — follow these

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

**Comments explain why, not what.** Match the density already in the file.

---

## 6. Layout

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
assets/css/        nora.css — the Tailwind source. NOT under static/: see §4
static/nora_home/       css, js, vendor. nh.css here is generated, gitignored
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

## 7. Progress log

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

## 8. Open questions for the user

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
