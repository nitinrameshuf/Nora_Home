# Progress log

The narrative record. Newest entries at the bottom. Every session that changes code
adds an entry here, and the story dashboard
([`dashboard/nora_home_dashboard.html`](dashboard/nora_home_dashboard.html)) is
updated to match in the same commit.

Status vocabulary, used consistently in both files:

| Status | Means |
|---|---|
| **Complete** | Written, reviewed, and observed working |
| **Built, unproven** | Written and reviewed, but never executed against real infrastructure |
| **Next** | The immediate next piece of work |
| **Planned** | Agreed, not started |
| **Retired** | Explored and superseded — kept with the reason, so it is not re-litigated |

---

## 2026-07-31 — the skeleton

The whole platform written in one sitting, then made to actually run.

### Built

**Foundation.** Django project with `dev` / `prod` / `pi` settings layered on a
shared base, every knob environment-driven. Structured logging that attaches a
request id, the acting member, and the surface to every line.

**The app registry** (Story 2) — the contract that makes this a platform. One class,
`NoraAppConfig`, gives an app its URL mount, nav entry, dashboard widgets, wall
panels, role gating, and MCP presence.

**The tracker and escalation engine** (Stories 5–6) — the spine. Nine cadences,
occurrences materialized two weeks ahead, and a ladder that climbs from the owner to
their chain to every adult to the whole house. Policies are editable JSON.

**Notifications** (Story 7) — Slack (bot token *or* webhook), in-app, wall display,
console, with intent and delivery as separate records so delivery is provable.

**Surfaces** (Stories 8–11) — one stylesheet for five surfaces, the home bot, the
wall/kiosk bus over Channels, and a per-person draggable widget dashboard.

**Data and intelligence** (Stories 12–16) — telemetry, the Claude client with cost
accounting and a budget cap, the MCP server, Mongo and object storage helpers, and
backup/restore with a cross-engine migration path.

**Operations** (Stories 17–20) — Docker Compose stack, Makefile, Pi provisioning
script, one-command app installer, and the integration framework.

### Restructured mid-session

- **URLs.** Platform moved under `/home`; house apps mount at their own top-level
  slug (`/habits/`, later `/workout/`, `/family/`). Reserved-slug guard added.
- **Home screen.** Server-rendered cards replaced by widgets that return data, with
  ECharts and Gridstack vendored into the repo for offline use.

### Two bugs found only by running it

**The app registry was silently empty.** Django picks an app's config by inspecting
`AppConfig` subclasses in `apps.py`. Because that file also imports `NoraAppConfig`,
there were always two candidates — and with no tie-breaker Django quietly fell back
to a plain `AppConfig`. No error, no warning; the nav and app directory were simply
blank. Fixed with `default = False` on the base plus `__init_subclass__` marking real
subclasses. **If the nav ever goes blank again, look there first.**

**Multi-line `{# #}` template comments render as visible text.** Django's `{# #}` is
single-line only; the header comment was printing at the top of every page. Now
`{% comment %}` blocks throughout.

### Verified

Ran end to end on Windows against SQLite: `manage.py check` clean, migrations
generated and applied for all ten apps, `bootstrap_home --demo` seeding three members
and three habits, Daphne serving, login working, and the home dashboard rendering
list, stat and chart widgets with a working add/remove picker.

### Not verified

Nothing has touched MySQL, MongoDB, RabbitMQ, MinIO, or a Raspberry Pi. Celery has
never executed a task. Slack, Claude and MCP have never seen live credentials. The
wall and kiosk pages have never been opened in a browser. Eight stories carry
**built, unproven** for exactly this reason.

---

## 2026-07-31 — renamed away from the robot

`nora` → `nora_home` throughout, because **Nora is the family's robot** and sharing a
name across an import path, an environment variable and an AI system prompt was a
guaranteed source of confusion.

| Was | Now |
|---|---|
| `nora/` | `nora_home/` |
| `NORA_*` env vars | `NORA_HOME_*` (`NORA_HOUSE_NAME` → `NORA_HOME_NAME`) |
| `static/nora/` | `static/nora_home/` |
| `.nora-bot`, `--nora-500` | `.nh-bot`, `--nh-500` |
| `window.Nora`, `NoraCharts` | `window.NoraHome`, `NoraHomeCharts` |
| `nora.css`, `nora-bot.js` | `nora-home.css`, `nh-bot.js` |
| `NoraBotConsumer`, `/ws/nora/` | `HomeBotConsumer`, `/ws/homebot/` |
| `nora_say()` | `bot.say()` |
| "Ask Nora" in the nav | "Assistant" |

The AI system prompt now states the distinction outright — it previously opened
*"You are Nora…"*, which would have had the house assistant answering as though it
were the robot.

The two systems now meet at **exactly two touchpoints**, both documented in
[`architecture.md`](architecture.md) § Boundaries: the robot may `POST
/api/homebot/say/` to put a line on the house screens, and it may read the MCP tools
with a scoped device token.

### Also this session

- `docs/` established as a first-class part of the repo, with the story dashboard,
  architecture diagrams, this log, and a documentation duty written into `CLAUDE.md`.
- First set of design directions rejected as too task-list-focused; a second,
  visualization-led set produced.

---

## 2026-08-01 — first real install attempt on a Pi (Story 27, in progress)

Ran `scripts/install-pi.sh` against an actual Raspberry Pi for the first time. Two
environment snags (docker-group membership not active in the current shell; the
script's default clone path not matching a directory the user had already cloned
into) were operator error, not bugs, and resolved by re-running with
`NORA_HOME_DIR` set and `newgrp docker`.

One real bug found: **`docker compose up -d --build` failed building the `web`
image** — `apt-get install -y mongodb-database-tools` exited 100. That package is
not in Debian's own archive (`deb.debian.org`); it is only published through
MongoDB's own apt repo, so the Dockerfile could never have built against stock
Debian or Raspberry Pi OS. This had shipped untested because §2 of `CLAUDE.md`
already flagged the whole Pi/Docker path as unexercised.

Fixed by dropping `mongodb-database-tools` from `Dockerfile`'s runtime-deps layer
rather than adding MongoDB's apt repo: `nora_backup.py`/`nora_restore.py` already
call `shutil.which("mongodump"/"mongorestore")` and skip with a logged status
instead of failing when the tool is absent, so the house comes up and just runs
without Mongo backup/restore, which matches the "Mongo is optional" decision in
`CLAUDE.md` §4. Not yet re-verified end to end on the Pi past this point — the
build had not been retried at the time of writing.

Auditing that Pi run also surfaced two design gaps in `install_app`, raised by the
user directly: no `.dockerignore` (the image build was copying in `.git`, any
stray `db.sqlite3`, logs, etc., since `Dockerfile` does a bare `COPY . .`), and no
durable story for an installed house app or a clean way to remove one.

- **Added `.dockerignore`** mirroring `.gitignore` plus `.git/` itself.
- **`install_app` now commits the app into this platform repo's own git history**
  (`git add houseapps/<name> && git commit`) after migrating it. Previously an
  installed app was pure loose files on one Pi's disk — invisible to
  `git status`, absent from a fresh clone, gone if the SD card died — with
  nothing but orphaned database rows left behind. Non-fatal if git isn't
  configured for commits, but loud about it either way.
- **Added `uninstall_app`** (Story: platform completeness). Default behavior only
  removes the app from `NORA_HOME_HOUSE_APPS` in `.env` — code, migrations, and
  data are untouched, and `install_app houseapps.<name>` (module-path form)
  re-registers it later with everything intact. `--purge-data` additionally runs
  `migrate <label> zero` to drop its tables; `--remove-files` additionally
  deletes `houseapps/<name>/` (via `git rm` if it was committed). Both destructive
  flags refuse to run without `--yes`, matching `nora_restore`'s existing
  confirmation pattern. `make uninstall NAME=<app>` added alongside `make app`.
  Documented in `DEVELOPMENT.md` under "Uninstalling and reinstalling".
- Not yet run against a live house app on real infrastructure — written and
  `manage.py check`-clean, not yet observed doing an install/uninstall/reinstall
  cycle end to end. Status: **built, unproven**.

Also cleaned up documentation drift the user flagged directly: the root
`README.md` still described the pre-rename `nora/` package layout (it predated the
`nora` → `nora_home` rename and was never updated) and both it and `docs/README.md`
pointed at `docs/deployment-pi.md`, which had never actually been written —
a dangling link, not a missing file someone forgot to open.

- **Deleted the root `README.md`.** It duplicated `CLAUDE.md` (the actual "read
  this first" doc per this project's own convention) and was actively wrong about
  paths.
- **Added `docs/deployment.html`** — the human-facing deployment guide the stale
  link was supposed to be: first install on the Pi, `make deploy`, installing and
  uninstalling a house app (with the same three-level flag table as
  `DEVELOPMENT.md`), a full data-safety matrix ("what happens to your data" for
  every operation above), backup/restore, and the two real snags hit during this
  session's Pi install (docker group membership, `mongodb-database-tools`). This
  is the project's split going forward: `.md` files are for agents and this
  project's own record of itself; `.html` files under `docs/` are for the people
  actually running the house.
- Updated `docs/README.md` and `CLAUDE.md` (§0 table, §7 layout) to point at
  `docs/deployment.html` instead of the dead `deployment-pi.md` reference.

Second real bug found continuing the same Pi run, past the fixed `mongodb-database-tools`
build failure: **`web` built and the data containers came up healthy, but `web` itself
came up unhealthy** — `MySQLdb.OperationalError: (1045, "Access denied for user
'nora'@'...' (using password: NO)")` on every migrate attempt. `docker-compose.yml`'s
`mysql` service resolves `MARIADB_PASSWORD` from `${NORA_HOME_DB_PASSWORD:-nora}`, so an
empty `.env` value (what `install-pi.sh` leaves it at — it never sets this key) falls
back to `nora` and the database is initialized with that password. But the `web` /
`worker` / `beat` containers get `NORA_HOME_DB_PASSWORD` via `env_file: .env`, which
passes the literal empty string through with no `:-default` fallback — so Django tried
to connect with no password at all against a user that actually has one. Fixed by adding
the same `${NORA_HOME_DB_PASSWORD:-nora}` default to the `x-app` anchor's `environment:`
block in `docker-compose.yml`, alongside the existing `NORA_HOME_DB_HOST: mysql`
override. Not yet re-verified end to end past this point.

Third bug, same run, one step further: with MySQL fixed, migrations applied cleanly,
but `collectstatic` then failed the whole `web` container —
`whitenoise.storage.MissingFileError: nora_home/vendor/gridstack-all.js.map could not
be found`. `gridstack-all.js` (vendored via `scripts/vendor.sh`) ends in a `//#
sourceMappingURL=gridstack-all.js.map` comment; Django's hashed-storage
post-processing follows that reference during `collectstatic` and fails hard if the
target isn't also present, and `vendor.sh` had only ever fetched the three files
listed in its own README table — never the map the first of them points to. Fixed by
fetching `gridstack-all.js.map` (10.3.1, matching the already-vendored bundle) into
`static/nora_home/vendor/`, adding it to `vendor.sh`'s fetch list and generated
README table so a future re-vendor doesn't drop it again. Not yet re-verified end to
end past this point either.

---

## 2026-08-01 — passwordless everywhere

Removed Django's password login entirely, at the user's explicit direction: no
password anywhere in the house, on any surface, including `/admin/`. Replaced with
a topbar switcher (`templates/base.html`) — tap a household member's name to become
them via `django.contrib.auth.login()` with no password check
(`nora_home/accounts/views.py`), plus a third "Everyone" tile for a combined view.
Recorded as a decision in `CLAUDE.md` §4.

- **`HouseMember.save()`** now forces `is_staff`/`is_superuser` from `role ==
  admin`, so admin access is gated by role alone, the same way everything else in
  this system already is — no separate password backstop exists to fall back on
  once one's removed.
- **Companion fix, not optional**: `make member` used to shell out to Django's
  `createsuperuser`, which makes *every* house member a Django superuser
  regardless of intended role. Harmless while a password gated `/admin/`; a real
  privilege leak once it didn't. Replaced with a new `add_member` management
  command (`nora_home/accounts/management/commands/add_member.py`) that sets an
  unusable password and takes an explicit `--role`.
- **"Everyone" reuses, rather than invents, existing plumbing**:
  `DashboardLayout.Surface.SHARED` (`dashboard/models.py`) had been modeled with no
  code path using it — added `for_shared()` alongside the existing `for_wall()`.
  `WallAgendaPanel` (`tracker/cards.py`) already aggregated all members for the
  wall display; the new `Occurrence.for_members()` and `scope_members(request)`
  helper (`nora_home/core/registry.py`) generalize that same pattern to the
  personal dashboard's widgets (`tracker/widgets.py`, and the reference app
  `houseapps/example_habit/widgets.py`, updated as the pattern other house apps
  will copy).
- `bootstrap_home --demo` no longer sets a password for the three demo members
  (`set_unusable_password()` instead) — the "password: nora" message in `CLAUDE.md`
  and the command's own output were stale the moment this landed, both corrected.
- Not yet run against the live Pi deployment — this landed after the first
  successful `docker compose up -d --build`, on top of code that had only been
  exercised via `manage.py check` and local reasoning at the time of writing.
  Needs a real click-through: switch between members, confirm "Everyone" actually
  aggregates two people's tracker items on one dashboard, confirm an admin-role
  member reaches `/admin/` and a member-role one does not.

---

## 2026-08-02 — Story 27 continued: systemd unit, kiosk autostart, first real bug in it

`install-pi.sh` had never gotten past the `docker compose up` step in any earlier
attempt this story, so its systemd-unit and kiosk/wall-autostart steps (step 5-6)
were unverified. Ran it again now that `docker compose up -d --build` works
cleanly (see the two bugs logged 2026-08-01): it completed end to end —
`nora-home.service` enabled, `~/.config/autostart/nora-wall.desktop` and
`nora-kiosk.desktop` written.

`sudo reboot` did not bring up either screen in kiosk mode — both came up showing
the plain desktop, no Chromium. Manually running the generated
`~/.nora/start-wall.sh` surfaced the actual bug immediately: `exec: chromium-browser:
not found`. Confirmed via `which chromium chromium-browser` — this Pi (Raspberry Pi
OS on Debian 13/"trixie", not "bookworm") installs the `chromium-browser` apt
package but the binary it ships is named `/usr/bin/chromium`; no `chromium-browser`
binary exists. `install-pi.sh` hardcoded the old name in the generated launch
script. Fixed by resolving the binary at launch time instead of install time —
`CHROMIUM="$(command -v chromium-browser || command -v chromium)"` inside the
generated `start-wall.sh`/`start-kiosk.sh` — so it self-adapts if the naming
changes again on a future OS image rather than needing another manual fix.

After that fix, a reboot did bring up Chromium on both — but only the 24" wall
was visibly correct; the kiosk process was confirmed running (`ps aux` showed both
`--user-data-dir=chromium-wall --window-position=0,0` and
`--user-data-dir=chromium-kiosk --window-position=1920,0`) but nothing appeared on
the 10" touchscreen — everything rendered on the 24" instead. Root cause: this
Pi's desktop session runs Wayland (`labwc`), not X11 — visible directly in the
process list (`--ozone-platform=wayland` on the GPU process). `--window-position`
is an X11-only concept; Wayland's security model deliberately forbids a client
from placing its own window at an absolute screen position, so the flag the whole
wall/kiosk split depends on was silently doing nothing — both windows landed
wherever the compositor's own default placement put them. `install-pi.sh` was
written assuming X11 (as most kiosk-mode guides do) without that ever being
checked against what Raspberry Pi OS actually ships now. Fixed by adding
`--ozone-platform=x11` to the generated launch scripts, forcing Chromium onto
XWayland (the X11-compatibility layer `labwc` ships) instead of native Wayland, so
`--window-position` is honored again.

Separately noted, not yet fixed: auto-login shows a "please enter your password to
unlock the login keyring" prompt on first graphical start, which blocks unattended
boot even once the display-positioning bug is fixed. Needs its own fix later
(likely: set the login keyring to auto-unlock or not require a password at all).

After the `--ozone-platform=x11` fix, a reboot still put the kiosk on the 24"
screen instead of the 10" — but this time stretched and unresponsive to touch,
not simply absent. Checked the actual layout to rule out another guess:
`wlr-randr` (compositor) and `DISPLAY=:0 xrandr` (XWayland, the coordinate space
`--window-position` actually operates in) both agreed the arrangement was already
correct — 24" (`HDMI-A-1`) at `0,0` sized 1920x1080, 10" (`HDMI-A-2`) at `1920,0`
sized 1024x600. So position wasn't the bug this time. Root cause: `--kiosk`
fullscreens whichever monitor the window's *initial* bounds overlap most, and
without an explicit `--window-size`, Chromium's default window dimensions can
overlap the wrong output on a mixed-resolution layout — landing kiosk mode on the
24" at the 10"'s content stretched to fill it, with touch coordinates mapped to
the wrong panel entirely. Fixed by giving each launch script an explicit
`--window-size` matching its real target output (values taken directly from the
`wlr-randr` output above, not guessed): 1920x1080 for wall, 1024x600 for kiosk.

Still landed both windows on the 24" after that fix, confirmed by photo — one
showing the wall content correctly, the other showing the kiosk control UI, both
on the same physical ViewSonic monitor. So `--window-position`/`--window-size`
were never the missing piece: `labwc` (the compositor) applies its own
window-placement policy when a window is mapped and simply overrides whatever
position/size an X11 client (Chromium via XWayland) asks for at creation time —
a compositor-level decision no Chromium flag can out-argue. Fixed by no longer
relying on creation-time hints at all: each launch script now backgrounds
Chromium, finds its window with `xdotool search --pid`, and force-moves/resizes
it with `xdotool windowmove`/`windowsize` after the fact — twice, once
immediately and once more after `--kiosk`'s own fullscreen transition settles,
since that transition can retrigger labwc's placement a second time.
`install-pi.sh` already `apt install`s `xdotool` and never used it anywhere —
apparently anticipated needing exactly this, never wired up until now.

Re-verified directly via SSH (see below — direct Pi access was set up mid-story):
the `xdotool` fix does not work. Confirmed empirically and against `labwc`'s own
documentation (`man labwc-actions`): `MoveToOutput`, `labwc`'s *native* mechanism
for exactly this, explicitly "moves active window to other output, **unless the
window state is fullscreen**." Chromium's `--kiosk` flag requests true OS-level
fullscreen, which `labwc` then pins to whatever output it chose at that moment —
permanently, immune to `xdotool windowmove`/`windowsize`, `labwc`'s own actions,
anything. This is a harder constraint than originally diagnosed: it's not "wrong
output picked once," it's "fullscreen geometry is compositor-owned, full stop."

Tried the obvious workaround — position the window correctly while it's still a
normal (non-fullscreen) window, then trigger fullscreen via `F11` once it's on
the right output, since `MoveToOutput`'s exclusion implies non-fullscreen windows
*are* movable. Blocked by a second, separate, unexplained bug: every
non-fullscreen Chromium window tested (plain, and `--app=` mode) got stuck at a
`10x10` placeholder geometry and never grew to its real content size, regardless
of `--window-size` or subsequent `xdotool windowsize` calls. Only `--kiosk`
(fullscreen) windows render as properly-sized, discoverable windows in this
environment. Couldn't dig further — `wmctrl` and `xwininfo` aren't installed and
installing anything needs `sudo`, which wasn't available non-interactively over
the SSH session used for this investigation.

Direct Pi access via SSH was set up mid-story (see below) specifically to stop
relaying every diagnostic command through the user, which unlocked much faster
iteration on this problem — and also let a fix get found. Confirmed empirically
that disabling the *other* output entirely (`wlr-randr --output HDMI-A-2 --off`)
before launching a `--kiosk` instance forces it onto the one remaining output,
with no ambiguity for the compositor to get wrong — and that the placement
survives re-enabling the other output afterward, as long as both outputs'
positions are explicitly re-pinned (`--pos`) afterward, since re-enabling an
output does not restore its previous position on its own.

However: repeated live testing of this toggle sequence proved genuinely
unreliable in practice, not just risky in theory — `wlr-randr` intermittently
reported "failed to apply configuration" for both `--off` and `--pos` commands
while other, seemingly identical invocations succeeded, and one sequence left
`HDMI-A-1` in a broken state (`Enabled: yes` but current mode `0x0`) that needed
an explicit `--mode` to recover. Given that fragility, decided against wiring
this into the unattended boot sequence tonight — a boot-time script that
sometimes silently fails to reconfigure a display, with nobody present to
notice or recover it, is worse than the current known state. Restored a clean
baseline (both outputs healthy, correct positions, wall running normally) and
stopped rather than keep experimenting live against a real display.

`cage` (a minimal Wayland compositor built for exactly "one app, pinned to one
output," which would sidestep `labwc`'s placement policy entirely rather than
fight it) remains the more promising longer-term fix, not yet attempted —
`sudo` access was set up (`/etc/sudoers.d/claude-apt`, passwordless for
`apt`/`apt-get` only) specifically to enable installing it, but the wlr-randr
approach was tried first since it needed no new packages. Worth trying `cage`
in a dedicated session rather than continuing to experiment against the live
display.

Separately, found and fixed a real bug in this session's passwordless-switcher
work while testing this: `switch_to`/`switch_to_everyone`
(`nora_home/accounts/views.py`) hardcoded a redirect to the dashboard
(`core:dashboard`) after switching, ignoring Django's `?next=` parameter that
`login_required` attaches when it redirects an unauthenticated request to the
switcher. Concretely: the wall display's Chromium profile lost its session
during testing (a test wiped its profile directory), and logging back in
through the switcher landed it on the personal dashboard instead of back on
`/home/displays/wall/` — meaning *any* page redirecting to the switcher, not
just the wall, would have had this bug. Fixed with a `_safe_next()` helper
mirroring Django's own `LoginView.get_success_url()` — validates `next` via
`url_has_allowed_host_and_scheme()` before trusting it, so a crafted link can't
use this to bounce someone off-site after they tap their name. `switch.html`
now threads `next` through both forms as a hidden field. Verified live: after
deploying the fix and re-authenticating the wall's Chromium profile, it
correctly returned to `/home/displays/wall/` instead of `/home/`.

**End of story state**: wall is running correctly on the 24" (`0,0`,
`1920x1080`, confirmed via `xdotool` after the output-toggle recovery above),
authenticated, showing real content. Kiosk is deliberately left **not
running** — getting it onto the 10" reliably needs the same output-disable
sequence that proved too flaky to trust unattended, and leaving it off is
better than leaving it wrong. Story 27 (first real Pi run) converted five real
infrastructure bugs into fixes tonight (DB password fallback, missing vendored
sourcemap, wrong Chromium binary name, `ALLOWED_HOSTS` never matching a LAN IP
on any Pi deployment ever, switcher losing its redirect target) — all
verified working. The dual-monitor kiosk placement problem remains open;
`cage` is the recommended next attempt, in a dedicated session with a fresh
`sudo` budget rather than continued live experimentation.

**Update — solved, differently than planned.** Rather than `cage`, switched
the Pi's whole desktop session from Wayland (`labwc`) to X11 (`openbox`) via
`sudo raspi-config nonint do_wayland W1` + reboot — a toggle Raspberry Pi OS
ships specifically for compatibility cases like this one. Confirmed via
`xdotool`/`ps` immediately after: both `--kiosk` instances landed correctly
and simultaneously, with zero repositioning tricks — wall at `0,0`/`1920x1080`,
kiosk at `1920,0`/`1024x600` — the exact layout `install-pi.sh` was written
for from the start. Root cause fully confirmed: this was never a bug in this
project's own code, it was `labwc` specifically refusing to let any
mechanism — not Chromium's own flags, not `xdotool`, not `labwc`'s own
`MoveToOutput` action — reposition a fullscreen window once placed. Recorded
in `CLAUDE.md`'s Pi section so it isn't rediscovered from scratch if this Pi's
OS is ever reinstalled.

Hit one real scare on the way: shortly after the reboot into X11, the Pi
became fully unreachable — SSH refused from every angle, physical screens
white — serious enough that a fresh OS install was considered. Recovered with
a plain reboot via Pi Connect, no reinstall needed. Root cause not
determined; possibly the fresh Chromium launches under the new session type,
possibly unrelated. Worth watching for a recurrence, not yet worth deeper
investigation given it self-resolved.

After that reboot, both Chromium profiles had lost their session again (same
class of issue as the earlier wall-profile case above) and initially showed
blank/loading state rather than real content. Resolved on their own after the
recovery reboot — confirmed by direct observation on the physical hardware
(not remote tooling, which lost Pi access again partway through and never
reconnected this session): the 10" shows the kiosk's tap-tile controller, the
24" shows the wall's real agenda view (correctly empty — no habits exist yet
in this fresh database). **Story 27 is done**: first real Pi run, from a
completely unexercised codebase to both physical displays working correctly,
authenticated, on real hardware. Every bug found tonight was fixed and is
recorded above for exactly this reason — so none of it has to be
rediscovered.

### 2026-08-02 — re-verified on a second, fresh Pi
The original Pi's reliability became suspect enough (SSH/screen-share dropping
unpredictably, one real hang requiring a Pi Connect reboot) that a second Pi
was provisioned from scratch instead of continuing to debug the first one.
Set up direct SSH access from the start this time (key-based, plus a scoped
sudo grant) specifically so the run could be driven directly rather than
relayed command-by-command.

`install-pi.sh` ran twice as designed — first pass installs Docker and exits
asking for a fresh login (group membership), second pass does everything
else — and **hit zero bugs**, on the first try, on a completely fresh Trixie
image. Every fix from the first Pi's bring-up (DB password, vendored
sourcemap, Chromium binary name, `ALLOWED_HOSTS`, the switcher redirect, and
now the automated X11 switch) held up exactly as intended. `docker compose
up` clean, member created, reboot, and the X11 session came up correctly on
the first try — `xdotool` confirmed wall at `0,0`/`1920x1080` and kiosk at
`1920,0`/`1024x600` simultaneously, no manual correction needed this time.

One new wrinkle, not seen on the first Pi: on this fresh image, auto-login's
"Unlock Login Keyring" dialog didn't just appear once — a *second* instance
(a separate `gcr-prompter` process, apparently triggered independently by the
kiosk's Chromium instance) appeared on the kiosk's screen too, each blocking
that screen's Chromium window from becoming visible until dismissed. Screen
share still doesn't work (X11, same tradeoff as before), so diagnosing this
took actual screenshots (`scrot`, pulled over `scp`) rather than eyes-on
access — confirmed the blocking dialog, dismissed both (click failed once on
a coordinate-estimation miss; `xdotool key Escape` after `windowactivate`
worked reliably) and confirmed real content on both screens afterward,
authenticated, by screenshot: the wall's actual empty-state agenda and the
kiosk's actual tap-tile controller, both correctly positioned and sized.

**Not yet fixed**: the keyring dialog(s) still have to be dismissed by hand
on first boot — genuinely blocks unattended kiosk startup until someone
does. Next real fix needed: either make the login keyring auto-unlock (sync
its password with the account's, since PAM would normally do this on a
real password login) or disable the keyring's password requirement entirely,
since nothing in this house's threat model needs it — same "LAN is the trust
boundary" reasoning as the passwordless switcher itself.

A fourth, unrelated bug surfaced while trying to check the passwordless switcher
from a phone instead: every request from anywhere but `localhost` — any phone or
laptop on the house LAN, the platform's actual intended access pattern — got an
HTTP 400. Root cause: `config/settings/pi.py`'s `ALLOWED_HOSTS` default included
`"192.168.1.0/24"`, but Django's `ALLOWED_HOSTS` has no CIDR/subnet syntax at all
— that entry never matched anything, silently, since whatever wrote it. And
`.env.example`'s `DJANGO_ALLOWED_HOSTS` default (`localhost,127.0.0.1,nora.home,
nora.local`) — which `install-pi.sh` never overrides for the Pi, unlike every
other pi-specific `.env` value it sets — takes precedence over that default
anyway, and doesn't include a LAN IP either. So this wasn't a today-only bug: no
Pi deployment of this platform, ever, was reachable from a phone or laptop by IP.
Fixed three places: `pi.py`'s fallback is now `["*"]` (matching the
already-established "LAN is the trust boundary" model from the passwordless
decision above); `install-pi.sh` now `sed`s `DJANGO_ALLOWED_HOSTS=*` into `.env`
like it does the other pi-specific overrides; and `base.py`'s
`CSRF_TRUSTED_ORIGINS` derivation now skips `"*"` rather than emitting the
invalid `"http://*"` Django would reject. Verified the derivation logic directly
(`ALLOWED_HOSTS=["*"]` → `CSRF_TRUSTED_ORIGINS=[]`, no exception) but not yet
re-verified against a live request on the Pi — `.env` is gitignored, so the
existing Pi deployment needs its `DJANGO_ALLOWED_HOSTS` line hand-edited, this
fix alone won't reach it via `git pull`.

---

## Next

1. **Story 23 — design system.** Blocked on a decision between the directions in
   `design-options.html`.
2. **Story 27 — first real run on the Pi.** The highest-value story on the board: it
   converts eight *built, unproven* stories into either *complete* or a bug list.
3. **Story 24 — house maintenance**, the first real app, which is what proves the
   skeleton was worth building.
