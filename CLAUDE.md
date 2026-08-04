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

**Every house app is required to have a folder under `docs/House_Apps/` with a
`README.md`.** `install_app` warns when one is missing, so it is enforced rather
than merely stated.

### What to update, when

| You changed… | Update, in the same commit |
|---|---|
| A story's status, or added one | [`docs/User/dashboard/nora_home_dashboard.html`](docs/User/dashboard/nora_home_dashboard.html) — the `STORIES` object, the summary counts, and the phase bars |
| Anything at all, in a working session | [`docs/Main_App/progress.md`](docs/Main_App/progress.md) — a dated entry, newest at the bottom |
| A component, boundary, or data flow | [`docs/Main_App/architecture.md`](docs/Main_App/architecture.md) — including the Mermaid diagrams |
| One subsystem's models, API, tasks, or gaps | The matching file in [`docs/Main_App/subsystems/`](docs/Main_App/subsystems/) |
| A published cross-app function | [`docs/Main_App/cross-functionality.md`](docs/Main_App/cross-functionality.md) — signatures are copied from the code, so keep them true |
| The app contract, or anything about the five surfaces | [`docs/Main_App/DEVELOPMENT.md`](docs/Main_App/DEVELOPMENT.md) |
| How you verify work on the Pi | [`docs/Main_App/testing.md`](docs/Main_App/testing.md) |
| A house app | That app's folder in [`docs/House_Apps/`](docs/House_Apps/) |
| A deployment, install, or uninstall step | [`docs/User/deployment.html`](docs/User/deployment.html) — for people, not agents; keep it in sync with `scripts/install-pi.sh`, the `Makefile`, `install_app`, and `uninstall_app` |
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
- **Deployment** — `docker-compose.yml`, `Makefile`, `scripts/install-pi.sh`. An
  `nginx` service terminates TLS on `:443` (self-signed — see §4) and is the only
  published entry point; Daphne's `:8000` is internal-only.
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
auto-detected by `install-pi.sh` via `timedatectl`; and a CSS specificity bug
(`.kiosk-grid` vs. the browser's own `[hidden]` rule) let a tapped app's control
screen render on top of the main menu instead of replacing it, fixed in
`static/nora_home/css/displays.css`.

Re-verified the same day on a second, freshly-imaged Pi (the first one's
reliability had become suspect) — `install-pi.sh` hit **zero bugs** end to
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

Two more one-click gaps closed the same day: `scripts/pre-install-pi.sh`
(run once via `sudo`, grants a validated `NOPASSWD` sudoers entry so nothing
in `install-pi.sh` prompts for a password afterward — no new capability, the
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
mapping. Both are now permanent: `install-pi.sh` §8 writes
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
`install-pi.sh` before this change, still pointed at the old
`http://localhost:8000` and had to be regenerated (re-running just
`install-pi.sh`'s `launch_script()` function, not the whole script, to avoid
sudo prompts over a non-interactive session for already-satisfied steps).
Killed and relaunched both Chromium instances by exact PID, then
screenshotted both physical screens: the wall shows the real authenticated
`/home/` dashboard — House vitals widget included, confirming the whole
stack survived the restart, not just nginx — and the kiosk shows its normal
button grid, connected, with no certificate-warning interstitial on either
screen (`--ignore-certificate-errors` did its job).

### Not done — pick up here
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
   unverified: the light theme on real hardware, and whether continuous
   animation plus backdrop blur holds up over hours rather than minutes.
2. **Celery worker/beat health unconfirmed.** Containers start, but showed
   `unhealthy` in `docker compose ps` at least once on the Pi — never confirmed a
   scheduled task (escalation sweep, backup) actually ran end to end.
3. **Slack, AI, MCP untested against live services.** No API keys were available.
4. **No tests.** `pytest` is configured; nothing is written.
5. **PWA manifest and service worker** — decided (§5) but not written.
6. **No favicon** — the logs show steady `/favicon.ico` 404s.
7. **Kiosk-drives-wall redesign and the Settings tab — built, unverified on
   the Pi.** The 24" wall now serves an iframe shell (`wall_live.html`)
   instead of pre-rendered ambient panels, and the 10.1" kiosk got
   context-sensitive per-app button screens (`nora_kiosk_controls` on
   `NoraAppConfig` — see `docs/Main_App/DEVELOPMENT.md`). A `Settings` page
   (`core:settings`) holds house-wide config, starting with a wall power
   schedule applied by a new host-side script + systemd timer via
   `xset dpms force`. All verified locally with Django's test client and
   direct logic tests, none of it seen on the physical screens yet.
   Specifically unconfirmed: whether `xset dpms force off` actually powers
   the panel down, and whether it's per-output or would blank the kiosk too
   — if the latter, the mechanism needs rethinking, since the kiosk has to
   stay on as the control surface.

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
`make up` now also generates a self-signed TLS cert on first run (idempotent
— see §4, "HTTPS via nginx"). The house serves on **https://<address>/home/**,
port 443, not `:8000` — nginx is the only published entry point. Your browser
warns once per device on first visit; see `docs/User/deployment.html`.

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
- Platform apps, registry, tracker, escalation, notifications, AI, MCP, datastores,
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
4. **Repo hosting and remote?** `scripts/install-pi.sh` needs `NORA_HOME_REPO` set.
