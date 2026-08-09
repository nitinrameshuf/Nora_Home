# Progress log

The narrative record. Newest entries at the bottom. Every session that changes code
adds an entry here, and the story dashboard
([`dashboard/nora_home_dashboard.html`](../User/dashboard/nora_home_dashboard.html)) is
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

### 2026-08-02 — kiosk touchscreen: two separate bugs, both fixed
Once both screens were rendering correctly, the touchscreen didn't respond
to touch at all (keyboard/mouse worked fine). Diagnosed in two stages rather
than guessed:

1. `lsusb` and `/proc/bus/input/devices` showed **no touch device at all** —
   not an X11/software problem, the Pi had never received a single touch
   event from the panel at the kernel level. Root cause: these budget HDMI
   touchscreens need a separate USB cable for touch, independent of the HDMI
   video cable, and that cable wasn't making a working connection to this
   specific Pi (it had been tested against a laptop separately, where it
   worked fine — confirming the panel and cable were both good). Swapping in
   a known-good micro-USB data cable fixed this immediately — the device
   showed up in `lsusb` (`Cadwell Laboratories, Inc. Paperlike HD-FT`,
   27c0:0818, a generic touch-controller chip ID reused across many
   whitelabel panels) and in the kernel's input device list.
2. With the device now present, X11 saw it too (`xinput list`) but its
   Coordinate Transformation Matrix was still the identity matrix — X11 has
   no automatic notion of which physical output a touch panel belongs to in
   a multi-monitor setup (unlike Wayland, which handled this automatically
   before tonight's switch), so touch coordinates were scaling across the
   *entire* combined 2944x1080 virtual screen instead of just the kiosk's
   own 1024x600 corner. Fixed live with `xinput map-to-output`, confirmed by
   the resulting matrix matching `kiosk_size/total_size` exactly
   (`0.347826 = 1024/2944`, `0.555556 = 600/1080`, `0.652174 = 1920/2944`),
   then made permanent via `/etc/X11/xorg.conf.d/40-touchscreen.conf`
   (`MatchIsTouchscreen "on"` + the same `TransformationMatrix`) so it
   survives reboots without needing `xinput` re-run by hand. Added to
   `install-pi.sh` (§8) so a future reinstall gets it automatically — the
   cable issue is hardware and out of scope for the script, but the mapping
   fix isn't. Confirmed working by the user tapping the physical screen.

### 2026-08-02 — 24" screen repointed from the ambient wall to the main app
Deliberate change, made after actually seeing the ambient view (`wall.html`)
running for real: the 24" screen now shows the full navigable app (`/home/`
— dashboard, sidebar nav, switcher) instead of the passive, non-interactive
wall view. `install-pi.sh`'s `WALL_URL` updated so this is what a fresh
install or reinstall gets by default. The `/home/displays/wall/` route and
`wall.html` itself are untouched and still work — this only changes which
URL the 24" screen's Chromium instance is launched against. Nothing else
about the split changes: the 10" kiosk still shows `kiosk.html`, and that
was always a remote control for the wall specifically, not a general
navigator — worth revisiting what the kiosk should do now that the 24"
isn't the passive ambient display anymore, but not changed tonight.

### 2026-08-02 — closing the two remaining install-pi.sh gaps
Asked directly whether `install-pi.sh` was "truly one click." Audited the
whole flow honestly and found it wasn't, for three reasons: the Docker-group
step required a human to notice a message and manually re-run the script; a
plain `sudo` password prompt was needed since no NOPASSWD grant existed by
default; and the keyring dialog (item 7) still needed dismissing by hand.
Fixed the two that were actually fixable in the script itself:

- **New `scripts/pre-install-pi.sh`** — run once via `sudo`, writes a
  `NOPASSWD: ALL` sudoers entry for the invoking user (`$SUDO_USER`),
  validated with `visudo -c` before being installed so a malformed file can't
  lock sudo out. Explicitly does not grant any new capability — the target
  account is already a full sudoer on a device already trusted; this only
  removes the password prompt, which matters because a fully unattended
  `install-pi.sh` run (or a future agent driving it over SSH) can't type a
  password at an interactive prompt at all.
- **Docker-group step now self-continues.** Previously `install-pi.sh`
  installed Docker, added the user to the `docker` group, then exited and
  told a human to log out, back in, and re-run it — group membership only
  applies to a new login session. Now it re-execs itself under `sg docker -c`
  immediately after the `usermod`, continuing in the same run instead of
  stopping. Not re-tested against a real fresh install (Docker was already
  present on the last Pi provisioned tonight, so this exact path never fired)
  — reasoned through carefully, but genuinely "built, unproven" until the
  next truly-fresh Pi confirms it.
- **Keyring fix from item 7 also applied and confirmed working**:
  `--password-store=basic` added to every Chromium launch flag set. Tested
  directly on the live Pi with a genuinely fresh, throwaway profile
  (`chromium-keyringtest`) — no "Unlock Login Keyring" dialog, no
  `gcr-prompter` process at all, and the window showed real content (the
  switcher page) immediately. Not just reasoned through this time — actually
  seen not happening.

The two structurally unavoidable steps stay manual, correctly:
`make member` (can't invent a real person's name), and each screen's one
first-ever tap on the switcher to establish its session (the entire point
of passwordless — nothing to automate around).

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

## 2026-08-02 — kiosk becomes a real remote control, and a Settings tab

Two related features, planned together since the wall/kiosk redesign
touched the same code both would build on.

**Kiosk drives the wall.** Since the 24" now shows the real app instead of
the old ambient view, the kiosk's old purpose (a fixed grid of buttons that
told the ambient view which of ~4 panels to show) no longer matched what
the wall displays. First design pass assumed the kiosk should become its
own interactive copy of the app — corrected after checking: the kiosk
should stay what it already architecturally was, a button remote, just
re-pointed at real app *pages* instead of ambient *panels*. Then corrected
again: the button set needed to be **context-sensitive** per app, not one
flat menu — tapping "Workout" should show workout-specific buttons on the
kiosk, not just switch the wall and leave the same generic menu showing.

Landed as: `NoraAppConfig` gained `nora_kiosk_controls` (`core/registry.py`),
the same shape as the existing `nora_wall_panels`/`nora_widgets` contract —
an app lists `{"title", "path"}` entries and gets its own kiosk button
screen for free, switched to locally the instant its top-level tile is
tapped (`kiosk.js: Kiosk.showScreen`), no round trip needed since the kiosk
is the only thing that can ever cause navigation in the first place (the
wall has no touch/mouse, so it can never navigate independently — this is
what let the design skip a wall→kiosk state-echo mechanism entirely).
Reference app (`houseapps/example_habit`) and `DEVELOPMENT.md` both updated
so a future app author — or their agent — finds this documented, not
rediscovered from the code.

Wall side: `/home/displays/wall/` now serves a thin iframe shell
(`wall_live.html`/`wall-live.js`) instead of the old pre-rendered-panels
page — the outer page and its websocket persist across navigation, only the
iframe's `src` changes, so a burst of kiosk taps doesn't cost a reconnect
each time. `X_FRAME_OPTIONS = "SAMEORIGIN"` already permitted this with zero
header changes. Old ambient `wall.html`/`wall.js`/`kiosk_panels`-based
`kiosk.html` flow deliberately left untouched, just unused by default.

Verified locally end to end (test client): wall renders the iframe pointed
at `/home/`, kiosk renders both the top-level menu and a per-app screen for
`habits` (the reference app, now declaring one control), the HTTP fallback
command endpoint accepts `navigate` too. Not yet seen on the physical
screens — that's next.

**Settings tab.** Reused rather than rebuilt: `HouseSetting`
(`core/models.py`) already existed as a generic, cached, admin-registered
key/value store with nothing reading or writing it from a real page — the
exact extensibility mechanism asked for. New `core:settings` page follows
the same plain-view pattern as `system_status`/`app_directory`; one setting
so far (a schedule for the wall's power), more to be added as plain form
fields over time rather than building a settings-registry framework for a
single current setting.

The real engineering problem: Django runs entirely in Docker, the physical
monitor is driven by Chromium on the Pi's own X11 session outside any
container — confirmed via direct search that no bridge between the two
existed anywhere in this codebase. Built one: a new management command
(`manage.py wall_power_state`) does the decision-making in Django, which
already knows the house timezone and has the settings store, printing a
bare `on`/`off`; a new host-side script (`~/.nora/wall-power.sh`, generated
by `install-pi.sh`) and systemd timer, running every 5 minutes outside
Docker, just execute that decision with `xset dpms force`. Chose DPMS over
`xrandr --output ... --off`, which this same session found genuinely
fragile for repeated unattended use earlier tonight (position drift, one
broken `0x0` mode needing manual recovery) — DPMS doesn't touch
output/CRTC configuration at all, so it's expected to be safer, but this
is reasoned, not yet proven: needs real verification on the Pi that it (a)
actually powers the physical panel down, (b) is per-output rather than
session-wide on this driver — if it turns out to blank the kiosk too, that
defeats the point, since the kiosk is meant to stay on as the control
surface. `nora-no-blank.desktop` updated to stop disabling DPMS outright
(it used to, which would have made `dpms force` permanently a no-op) while
still disabling idle-based auto-blank.

**Not yet done**: none of this has been deployed to or seen on the real Pi
yet — verified locally only. Also caught mid-build and fixed before it
shipped: the systemd wall-power service needs `XAUTHORITY` set explicitly,
since a system-level service doesn't inherit the graphical session's X11
auth just because `DISPLAY` is set — added `Environment=XAUTHORITY=%h/.Xauthority`
before this was ever run for real, not after discovering it broken.

### 2026-08-02 — kiosk remote control and Settings tab, verified live on the Pi

Deployed the above to the Pi and checked every open question against real
hardware rather than trusting the local-only verification.

**DPMS is session-wide, not per-output** — the open risk flagged above.
Tested directly (`xset -display :0 dpms force off`) and confirmed by the
user looking at both physical screens: the wall *and* the kiosk both went
dark, not just the wall. `vcgencmd display_power` was tried as a
per-output alternative and found unsupported on this Pi 5's firmware
("Command not registered"). Given `xrandr --output ... --off` was already
proven fragile for unattended use earlier in this same story (position
drift, one broken `0x0` mode), asked the user directly rather than guess:
confirmed both-screens-off is acceptable, since the platform itself keeps
running underneath either way and the kiosk being dark for the scheduled
window is a fair trade against a flakier per-output mechanism. Corrected
`templates/core/settings.html`'s copy, which had assumed per-output
control, to say so plainly.

**A real, pre-existing timezone bug, found by testing the schedule
directly**: `manage.py wall_power_state` uses Django's own timezone-aware
clock as designed, but the Pi's `.env` still had `.env.example`'s
placeholder `DJANGO_TIME_ZONE=America/Los_Angeles` — the actual host
(`timedatectl`) is `America/New_York`. Not a bug in tonight's feature; a
gap that existed since the Pi was first provisioned and just happened to
surface now because this was the first thing to actually read that
setting and compare it against wall-clock time. Fixed the live Pi's
`.env` directly, and added auto-detection to `install-pi.sh` so a future
install or reinstall gets the host's real zone automatically instead of
the placeholder:
```bash
PI_TZ="$(timedatectl show --property=Timezone --value 2>/dev/null || true)"
```

**One real bug in the new kiosk screens themselves**, caught by an actual
screenshot, not just code review: tapping an app tile correctly switched
the wall via the iframe, but the kiosk's own screen showed the tapped
app's controls (e.g. habits' "← Apps" / "All habits") stacked *underneath*
the still-visible main menu grid, instead of replacing it. Root cause:
`.kiosk-grid { display: grid }` and the browser's own default
`[hidden] { display: none }` are equal CSS specificity, and this
project's stylesheet loads after the browser's — so the class rule won
the cascade and silently defeated the `hidden` attribute on any element
carrying both. Fixed with an explicit `.kiosk-grid[hidden] { display:
none; }` in `static/nora_home/css/displays.css`.

Redeployed, killed and relaunched both Chromium instances, and re-verified
by screenshot and simulated touch (`xdotool`) end to end: tapping "Habits"
on the kiosk switches the wall's iframe to `/habits/` and switches the
kiosk to the habits-only control screen (main menu correctly hidden this
time); tapping "← Apps" returns the kiosk to the main menu locally without
disturbing the wall's current page, exactly as designed — the kiosk is the
only side that can ever navigate, so there's no wall→kiosk state to echo
back. The wall-power systemd timer (`nora-wall-power.timer`, installed by
an earlier run of `install-pi.sh` tonight) is confirmed enabled and firing
every 5 minutes; `manage.py wall_power_state` returns a correct `on`/`off`
against the now-fixed timezone.

**Story is now fully verified live, not just built.** All three of
tonight's open risks (DPMS scope, timezone correctness, kiosk screen
switching) were checked against real hardware and either confirmed
working or fixed.

## 2026-08-03 — Story 23 decided and built: the living background, and a real weather integration

Two rounds of `docs/design-options.html` mockups were rejected as generic —
recognizable as "an AI-generated dashboard" no matter the palette, because a
sidebar-plus-card-grid *is* that template regardless of colour, and a first
pass at fixing this by making the wall passively ambient was also rejected
("forget about that ambient wall, i dont want that entirely itself"). What
landed instead: the real season, time of day, and actual outside weather
composited as a living background *behind* the real, fully interactive app
— the wall keeps showing `/home/` (or whatever the kiosk pointed it at), the
kiosk keeps being buttons-only, neither changes shape. "Charm outside,
polish inside" — the atmosphere carries the personality, the data sitting on
top of it in translucent glass panes stays disciplined.

Asked to "code that real time weather now" rather than keep it as a mockup,
so this landed as working code, not another round of `design-options.html`:

- **`nora_home/ui/scene.py`** — season from the date plus the house's own
  latitude (flips correctly south of the equator), day/night from the
  *actual* sunrise and sunset for the house's location, not fixed clock
  hours. Shared by a context processor (first paint, no flash of the wrong
  sky) and a small JSON endpoint (`core:weather_current`) both the wall
  (through the app it iframes) and the kiosk poll every 5 minutes, so two
  screens that each sit open for hours can't quietly drift onto different
  seasons or times of day.
- **`nora_home/integrations/providers/weather.py`** — the platform's first
  concrete integration, exercising the integration framework for real for
  the first time since it was written (`Story 20`'s "zero concrete
  integrations exist, the framework has never polled anything" is no longer
  true). Open-Meteo, chosen specifically because it needs no API key — only
  `NORA_HOME_LAT`/`NORA_HOME_LON`, defaulted to New York City to match the
  Pi's already-configured timezone. WMO weather codes bucket down into the
  four states the background actually renders: clear, cloudy, rain, snow.
  Registered via `IntegrationsConfig.ready()`, seeded by `bootstrap_home`.
- **`static/nora_home/css/nh-scene.css`** — the scene itself (sky gradient,
  sun/moon position, horizon silhouette and foliage, rain/snow/cloud/sun-ray
  overlays), plus a retrofit of `.card`, `.sidebar`, and `.kiosk-tile` onto
  translucent, blurred glass so text stays legible over any sky, in both
  light and dark theme. Loads after `nora-home.css` so it can override by
  cascade order alone, without needing to touch the base stylesheet.
- **`static/nora_home/js/nh-scene.js`** — the only client-side logic is
  "poll and apply." All the actual season/daypart/weather computation stays
  server-side in `scene.py`, which is what guarantees the wall and kiosk
  can never disagree about what moment it is — there's exactly one place
  that decides.

**Verified, not just written**: a real fetch against the live Open-Meteo API
during this session returned genuine current conditions (light rain, 24.9°C,
real sunrise/sunset for the default NYC coordinates) and `current_scene()`
correctly derived `summer`/`night` from them. `manage.py check` clean,
fresh `migrate` + `bootstrap_home --demo` run clean (no new migrations —
this reuses the existing `HouseSetting`/`Integration`/`Series` tables), and
`/home/`, `/home/displays/kiosk/`, and `/home/settings/` all render via
Django's test client with matching `data-season`/`data-daypart`/
`data-weather` attributes on `<html>`.

**Not yet done**: this is the engine and a first real skin, not the full
Story 23 scope. No new type scale, no per-component pass across every
widget, no verification at 375px yet — `.card`/`.sidebar`/`.kiosk-tile`
cover most of the visual surface area by virtue of the existing "widgets
return data, not HTML" convention, but that's a happy consequence of the
existing architecture, not a claim that every surface has been individually
checked.

**Deployed and seen live on the Pi the same session.** One real bug
surfaced doing this, unrelated to the living background itself:
`bootstrap_home`'s `_storage()` only ever caught `StorageUnavailable`, but
this Pi's actual failure is a MinIO signature mismatch (`botocore
ClientError`) that isn't that type — it was propagating all the way up and
silently killing every step after it, including the new `_integrations()`
seeding step. Fixed by catching the broader exception the same way the rest
of the codebase treats object storage as optional. After that,
`bootstrap_home` correctly seeded the weather integration, a manual fetch
against the live API returned real conditions (cloudy, 24.8°C, correctly
bucketed), and `current_scene()` derived `summer`/`night` from them exactly
as it does locally. Screenshots off the physical wall and kiosk (`scrot`
over SSH) show the atmosphere genuinely rendering — drifting cloud shapes,
a green summer horizon with trees, the home bot sitting on the hillside —
behind the real app on the wall and the real button grid on the kiosk, both
legible. Re-tested the kiosk-remote-control flow from the previous story on
top of the new skin to check for regressions: tapping "Habits" still
correctly navigates the wall's iframe and swaps the kiosk to the
Habits-only control screen. Not yet tested: light theme on real hardware,
and whether continuous animation plus backdrop blur on every pane holds up
over hours rather than a few minutes.

## 2026-08-03 — cross-app aggregation, made explicit and given its second example

Asked directly what a house app needs to follow so `/home/` can review data
from every app collectively, while still letting apps build anything —
followed by "why telemetry?" and a concrete question: can a workout app
schedule something in a todo app, and does anything separate logs from
alerts. All three were mostly already true of the platform; this session
made the pattern legible and gave it a second working example.

**The answer was already sitting in `nora_home/tracker/widgets.py`**:
`TodayWidget`/`OverdueWidget`/`ReliabilityWidget` query every open/overdue
`Occurrence` with no `app_slug` filter at all. Any app that calls
`register_trackable()` shows up in everyone's cross-app summary automatically
— that's the whole mechanism, and it already worked, just wasn't stated
anywhere as *the* pattern to follow.

**Telemetry didn't have the equivalent**, so it got one:
`nora_home.telemetry.widgets.HouseVitalsWidget` — a `ListWidget` querying
every active `Series` with no `app_slug` filter, mirroring `TodayWidget`
exactly. Added alongside it: a `category` field on `Series` (migration
`telemetry.0002_series_category`), threaded through `define_series()`, so
the home screen can group numbers by theme ("health", "house", "fitness")
instead of only by which app happens to own them — the one thing a private
metrics table could never give you. `list_telemetry_series` (MCP) and the
admin now surface it too.

Verified with real, heterogeneous data rather than a single test app: the
widget correctly aggregated a demo house-telemetry reading, the (seeded but
inactive) robot's battery series, and the weather integration's own
temperature reading — three unrelated sources, zero widget code written for
any of them beyond calling `record_reading`. Along the way, cleaned up the
weather integration's own series: it was relying on `record()`'s auto-create
fallback and showing up as "Weather Temperature_C" — now explicitly named
"Outside temperature" and categorised `house` via `define_series()`, which
is also now the documented example in `DEVELOPMENT.md`.

**The workout → todo question** turned out to be a naming confusion worth
closing explicitly in the docs, not a missing feature: there is no separate
"todo app" to reach into — `tracker` *is* the shared todo/scheduling spine,
and every app already calls it directly for its own items. What's actually
forbidden is importing another app's own models/private logic; that stays
signal-only (`nora_home.core.signals`), unchanged. `DEVELOPMENT.md`'s
"Talking to other apps" section now says this outright, with a runnable
example, rather than leaving `app_slug` looking like a permission gate.

**Logs vs. alerts**: confirmed the platform already has four distinct tiers
— structured `logging` (developers only, on disk), `nora_home.core.audit`
(durable, queryable, never pushed to anyone), telemetry readings (silent
until a threshold fires), and `notifications.api.notify()`/`notify_house()`
(the only one of the four meant to interrupt a person). This was true in
code already; `DEVELOPMENT.md` now has a table making it explicit, since
nothing previously said audit and notifications weren't the same thing.

Verified: `manage.py check` clean, migration applied, `/home/` and
`/home/measurements/` render, and the widget's payload directly inspected
end to end with real data from three different sources.

---

## 2026-08-03 — HTTPS on :443, via nginx, with a self-signed cert

Asked "how do I access the site on a laptop" led to "why is it on :8000, what
would it take to put it on 443" — answered, then asked for outright: nginx in
front, a real cert, port 443.

No public domain exists for a Pi on a house LAN, so there is no CA that could
ever issue this house a certificate a browser trusts by default. Went with
self-signed rather than standing up a private CA (`mkcert`) or acquiring a
domain purely to satisfy Let's Encrypt's DNS-01/HTTP-01 validation — asked the
user directly rather than assuming; they picked self-signed, and nginx-only
(no port 8000 left reachable) over leaving both open.

**What changed**: an `nginx` service (`nginx/nginx.conf`) now terminates TLS
on :443 and redirects :80 to it, proxying to `web:8000` over the internal
Docker network — `web` no longer publishes a host port at all, matching the
existing "nginx only" decision. `scripts/gen-self-signed-cert.sh` generates a
10-year self-signed cert (SANs: localhost, nora.home, nora.local, 127.0.0.1,
plus the Pi's LAN IP at generation time), idempotent, called by both
`install-pi.sh` and `make up` (new `nginx/certs/nora-home.crt` prerequisite).
Daphne was already started with `--proxy-headers`, and `prod.py` already had
`SECURE_PROXY_SSL_HEADER` gated behind `NORA_HOME_FORCE_HTTPS` — both
anticipated a TLS terminator in front, they just never had one until now.

**The subtle bug this would have shipped without local testing first**:
`prod.py` turns HSTS on for a full year whenever `SECURE_SSL_REDIRECT` is
true. With a self-signed cert, that's actively dangerous, not just
unnecessary — once a browser accepts an HSTS max-age for a host, Chrome and
Firefox both withdraw the "proceed anyway" click-through for an *invalid*
cert on that host, no exceptions. The first cert rotation (or the Pi's LAN IP
changing, which the cert's SAN is keyed to) would have permanently locked
every laptop and phone out, with no way back in except clearing HSTS state on
every device by hand. `config/settings/pi.py` now forces
`SECURE_HSTS_SECONDS = 0` regardless of `SECURE_SSL_REDIRECT`, with the
reasoning written down so it isn't "helpfully" turned back on later.

**Verified locally**, against real `config.settings.pi` settings (not
`dev.py` — switched `.env` over deliberately, then reverted it after,
since this laptop's normal setup is SQLite/dev for other testing) via
`docker compose up`: HTTPS on the mapped port returns `200` with no
`Strict-Transport-Security` header; plain HTTP redirects to HTTPS; Daphne's
`:8000` is confirmed unreachable directly from the host; `manage.py check
--deploy` shows only the two already-understood, deliberate warnings (HSTS
off by design, `X_FRAME_OPTIONS=SAMEORIGIN` by design for the wall's
iframe); and nginx correctly relays a `/ws/` upgrade request through to the
Channels layer — got an application-level 403 for lacking auth, not a
proxy-level failure, confirming the Upgrade/Connection headers actually reach
Django. Also found and fixed live: `gen-self-signed-cert.sh`'s `hostname -I`
call aborted the entire script under `set -e`/`pipefail` wherever that flag
isn't supported — degraded to `|| true` instead of failing cert generation
over a cosmetic SAN entry.

**Then deployed for real, same session.** `git pull --ff-only` on the Pi,
`.env` given the same three new vars, `gen-self-signed-cert.sh` run there —
its SAN picked up the Pi's actual LAN IP (`192.168.1.253`) automatically —
and `docker compose up -d` brought nginx up alongside the rest. Repeated the
same checks directly on the Pi: HTTPS 200 with no HSTS header, HTTP redirect,
`:8000` unreachable from the host, all services healthy.

The part that actually mattered: the wall and kiosk's Chromium launch
scripts (`~/.nora/start-wall.sh`, `start-kiosk.sh`) were generated by an
*earlier* run of `install-pi.sh`, before this change, so they still pointed
at `http://localhost:8000` — running unchanged, they would have shown a
connection error on both physical screens the moment this deployed.
Regenerated them by extracting and re-running just `install-pi.sh`'s
`launch_script()` function (not the whole script — that would have hit
sudo prompts for already-satisfied package/systemd steps over a
non-interactive SSH session) with `NORA_HOME_HTTPS_PORT` and the new URLs.
Killed and relaunched both Chromium instances by exact PID (the established
recovery pattern from earlier sessions), then screenshotted both physical
screens: the wall shows the real authenticated `/home/` dashboard —
including the House vitals widget with a live outside-temperature reading,
confirming the whole stack survived the restart, not just nginx — and the
kiosk shows its normal button grid, connected, with no certificate-warning
interstitial on either screen. `--ignore-certificate-errors` did its job.

Story 18 is back to *complete* — see the dashboard.

---

## 2026-08-03 — topbar decluttered into one profile icon; it now carries the sun/moon

Three rounds of feedback on the same corner of the screen, each building on
the last, all found by pointing at real screenshots rather than describing
the problem abstractly.

**"Add a widget / Rearrange / the member switcher / Theme" were four separate
elements** crowding the top-right, wrapping onto two rows the moment a page
had its own action buttons. Replaced with a single avatar-icon trigger
(`.profile-trigger`/`.profile-avatar`, `templates/base.html`); everything
else — a page's own `{% block actions %}` content, "Signed in as X", the
rest of the household, Theme — moved into its dropdown. `.btn` buttons
already used by page-specific actions (`home.html`, `tracker/board.html`)
needed no changes themselves: `.profile-dropdown .btn` resets them to a flat
menu row only inside this dropdown.

**Then**: "combine the sun or moon from the background into the profile
icon... this will remove clutter" — the ambient orb (part of the Almanac
living background, `nh-scene.css`) sat right next to the new avatar circle,
two competing circular things near the top. The icon's background/box-shadow
now picks up the same daypart-driven gradient as the orb itself (dawn/noon/
dusk/night), so it reads as an extension of the scene instead of bolted-on
chrome — a small glowing sun or moon with the member's initial on it.

**Then**: "remove the sun from the background, the icon takes care of it,
right?" — checked rather than assumed: the kiosk (`templates/displays/
kiosk.html`) is a standalone template with no topbar and no profile icon at
all, so it's the *only* surface left with no other way to signal day/night.
The wall didn't need special-casing — it shows `/home/` (which has the icon)
in an iframe. Scoped the hide to `:root:not([data-surface="kiosk"])` rather
than deleting the orb outright, so the kiosk keeps its sun/moon exactly as
before.

Each of the three changes was verified the same way: rendered locally first
(Django test client / `manage.py check`), then deployed and screenshotted on
the actual physical wall and kiosk — the last round specifically to confirm
the orb really did disappear from the wall's sky while staying on the
kiosk's, not just reasoned through from the CSS.

---

## 2026-08-03 — invisible text across most of the app, and a 500 on Status

"Pull the visuals for different screens... text is not legible in many
cases, in either theme." Asked for exactly that rather than guessing: SSH'd
onto the Pi, screenshotted Home, Tracker, Alerts, Integrations, Status, App
Directory, and the 404 page, in both themes.

**Root cause**: `.card`/`.sidebar`/`.kiosk-tile` got the living background's
glass-pane retrofit; nothing else did. Tracker's item list, Alerts' empty
state, App Directory's table, every `.empty`/`.dash__empty` box, and the
404/500 pages all put text directly on the scene, using `--text`/
`--text-faint` colours chosen for contrast against a flat `--bg` — not
against a sky that swings from near-black at night to near-white at noon,
*independently* of the light/dark theme toggle. Light theme's dark text
vanishes on a night sky; dark theme's light text vanishes on a bright one —
exactly "either theme," and exactly why only some pages looked broken (only
the ones with real cards were spared).

**Fix**: a theme-aware text-shadow halo on `.main` (dark shadow behind light
text, light shadow behind dark text) as a baseline for anything sitting
directly on the scene — harmless where a card's own glass already carries
the contrast. `.empty`/`.dash__empty` also got an actual background, since a
dashed box with invisible text inside reads as broken chrome, not
atmosphere.

**Also found chasing why Status looked blank**: it wasn't contrast there,
it was a 500. `probe.host|default:probe.reason` in
`templates/core/system_status.html` raises a hard `VariableDoesNotExist`
whenever a service dict has neither key (database, disk, cpu_temperature
never have `host` or `reason`) — Django's `default` filter tolerates a
missing *primary* variable but not a missing *argument*. Nobody had hit this
because prior verification passes checked `/home/health/`'s JSON directly,
never the templated page. Switched to `{% if %}`/`{% elif %}`.

Verified by re-screenshotting the exact same pages after deploying — Status
now renders (200, not 500) with every probe visible, and the previously
invisible text (Tracker's "Clear for today.", Alerts' "Nothing to report",
Integrations' lede paragraph, the 404 page's body copy) is legible in both
themes. This also closes the "light theme on real hardware" item that was
sitting in Next below — checked directly this session, not assumed.

**Turned out incomplete**: told directly — "looks good in the bright
theme, but still illegible in the dark theme... so blurry too" — with
screenshots of both. The blurred `text-shadow` alone wasn't enough:
`--text-faint` (`#62778c`, identical in both themes) sits close in hue
*and* luminosity to the sky's own medium-blue tones at a lot of scroll
positions, so a wide soft glow just smeared into haze around the letters
rather than an edge — legible in light theme, where the white glow had
real headroom against that blue, not in dark, where the darker glow was
too close in value to read as a rim rather than a smudge. Switched the
primary mechanism to `-webkit-text-stroke`, which traces the actual glyph
outline (vector, not blurred) so it stays a hard edge regardless of how
close the fill and the sky happen to be — reset back to nothing inside
`.card`/`.dash-tile`, where it isn't needed. Verified with a fresh
screenshot of the same Displays page that was reported broken.

**Also reported in the same message, unrelated**: the kiosk always showed
"offline, last heartbeat never" on that same Displays page, despite being
on and in active use. Root cause: `KioskConsumer` (`nora_home/displays/
consumers.py`) never registered a `Display` row or handled a heartbeat at
all — only `DisplayConsumer` (the wall) did both. `kiosk.js` never even
sent one. Both were genuinely missing, not misconfigured — mirrored the
wall's registration/heartbeat pattern onto the kiosk consumer and added the
matching 30s heartbeat send to `kiosk.js`. Verified two ways: querying
`Display.objects.all()` directly on the Pi after a fresh reconnect (both
rows `online=True` with matching timestamps) and a screenshot of the same
Displays page.

---

## 2026-08-03 — the text-stroke fix didn't hold up either; replaced the technique

The `-webkit-text-stroke` fix above looked right in a screenshot and was
still wrong: reported back with photos of the actual 24" panel and a
MacBook M4's retina screen, both showing the same ghosted/blurry text the
very first fix had — worse on retina than on the 24".

Both attempts so far had the same flaw in common, just not named yet: a
blurred `text-shadow` and a sub-pixel `-webkit-text-stroke` are both font
*rendering* tricks — how they rasterize depends on each device's own font
hinting and pixel density, which a stylesheet doesn't actually control.
That's exactly why a fix could look fine in one screenshot and ghost on
real hardware, worse again at a different DPI: two different renderers
making two different calls about the same sub-pixel instruction.

Stopped trying to out-tune a technique that was never going to be
reliable, and used the one mechanism already *proven* to look identical
everywhere: `.card`'s real, opaque-ish backdrop — plain alpha compositing,
nothing to do with font rasterization. Moved that onto `.main` itself
(`background: rgba(...); backdrop-filter: blur(...)`, same as `.card`),
removing the stroke/shadow entirely. First pass (0.4 opacity) left the
lede paragraph a little soft specifically where it crossed a bright
cloud — not a rendering artifact this time, just needed more margin at
the brightest end of the sky's range — bumped to ~0.5, matching `.card`'s
own strength. Verified at both 1x and a simulated 2x (retina) scale via
Playwright before touching the Pi, then confirmed on the physical wall
itself. Less open sky shows through outside the cards now, a real
trade-off, but every test so far — both scales, both themes, the actual
hardware — reads clean, with nothing left riding on how a given screen
happens to rasterize a stroke.

---

## 2026-08-03 — Story 21 (Test Suite) scoped, deliberately not started yet

Asked directly: do we have tests that could have caught today's bugs (the
Status-page 500, the kiosk's missing heartbeat) without manual
screenshotting each time, and that a new house app would automatically get
covered by too? No — confirmed by checking, not assumed: `pytest`/
`pytest-django` are configured, zero test files exist anywhere in the repo.

Talked through scope rather than just writing code: route/widget smoke
tests (walking `all_widgets()`/`navigation()` rather than one test per
page) plus Channels `WebsocketCommunicator` tests for the heartbeat/relay
logic would have caught both of today's bugs directly, cheaply, and — this
was the useful distinction — test *shape*, not internals, so they survive
a refactor instead of needing to be rewritten by one. Deep logic tests
(the escalation ladder, the cadence scheduler — the two things that most
need coverage, since they run unattended and fail silently) are the
opposite: their internals are exactly what a cleanup pass might change.

Asked whether to write tests before or after "cleaning up the base app."
Landed on: smoke tests *first*, specifically as the safety net a cleanup
pass wants, not something to do after it — deep logic tests wait until
after cleanup so they aren't rewritten twice. Decided to defer the whole
thing until that cleanup pass happens, rather than start now. Scoped in
full on Story 21 (dashboard) rather than left as a one-line "no tests"
note, including the explicit boundary: visual/contrast bugs and real
hardware behavior are not pytest's job and still need what this session
did by hand.

---

## 2026-08-03 — the legibility fix from earlier today didn't hold, root-caused for real this time

Reported again, with fresh screenshots: the Displays page's intro paragraph
and the sidebar's nav labels were still barely legible in dark theme, and
asked separately to make dark theme the default.

Checked the default first, directly rather than assuming: `data-theme="dark"`
is already hardcoded on `<html>` in every template (`base.html`, `kiosk.html`,
`wall.html`, `wall_live.html`, `accounts/switch.html`), and there is no
`prefers-color-scheme` media query anywhere in the CSS overriding it — only
`:root[data-theme="light"]` token overrides. A fresh Playwright context with
no stored preference confirmed this renders dark. Dark already was the
default; that wasn't the bug.

The real bug: the backdrop-opacity fix from earlier today's session
(`.main` at 0.54 alpha, `.sidebar`/`.card`/`.kiosk-*` never touched at all,
still 0.34/0.46) was tuned against one sky state and never checked against a
bright one. Worked through the compositing math: at 0.34-0.56 alpha, a
bright overcast midday sky blended through pulls the composited background
up into the same mid-grey range as `--text-faint`/`--text-dim`, collapsing
contrast to near zero — worst on `.sidebar`, which had the lowest opacity of
all of them and was never bumped in the first fix, matching exactly which
element the new screenshot flagged as worst.

Fixed two ways together: pushed `.sidebar`/`.card`/`.main`/`.kiosk-header`/
`.kiosk-tile`/`.kiosk-controls`/`.empty` to ~0.86 alpha (both themes) so the
composited backdrop stays reliably dark, or paper-white in light theme,
regardless of daypart/weather instead of chasing one sky state; and
brightened `--text-dim`/`--text-faint` one token step in dark theme
(`ink-300`/`ink-400` → `ink-200`/`ink-300`) for real contrast margin against
that now-darker backdrop, since the user named this specifically as a text
color issue, not just a background one.

Verified against the live Pi over HTTPS with Playwright, not just reasoned
through: logged in passwordlessly, screenshotted `/home/displays/` in a
fresh context (confirming dark-by-default) — the exact page from the report,
now legible throughout — and again with `data-theme` forced to light,
confirming the same fix holds there too.

## 2026-08-03 — that fix overcorrected: the living background stopped living

Reported immediately after the above shipped: "thematic elements are barely
visible now, know? day, night, seasons?" Pushing every glass pane to one
flat ~0.86 alpha did guarantee contrast at the worst-case sky (bright
overcast noon), but it applied that same near-opaque scrim at every daypart
— night's already-dark sky got exactly as much scrim as noon's near-white
one, so the panes looked identical regardless of season, time of day, or
weather. That's the entire premise of "Almanac" undone by its own
legibility fix.

Replaced the flat alpha with `--pane-alpha`, a custom property keyed off
the `data-daypart` attribute the scene system already sets server-side:
night ~0.34 (its sky is already close to black, barely needs a scrim),
dusk/dawn ~0.58-0.68, noon ~0.84 (still the worst case, still needs the
most). Light theme mirrors this inverted, since there the problem is a dark
night sky under a near-white pane rather than a bright day sky under a
near-black one. `.sidebar`/`.card`/`.main`/`.kiosk-*`/`.empty` all read
from the same variable, so there's one dial instead of duplicated numbers
per selector.

Verified on the live Pi by forcing `data-daypart` through all four values
via Playwright and screenshotting each: noon and night are both fully
legible, and now visibly distinct again — noon a cool charcoal-blue, night
deep navy with the profile icon showing its moon, dusk warm plum/rose,
dawn terracotta.

**Reverted, same day.** Told directly: opacity is the wrong lever
regardless of how it's tuned — flat or daypart-scaled, it's still fighting
the scene to make text readable, and the fix should live in text color
instead. `nh-scene.css`/`nora-home.css` rolled back to `28ccbbd` (the
state before today's opacity work): `.main` alone at its earlier flat
0.54/0.56 alpha, `.sidebar`/`.card`/`.kiosk-*` back to 0.34/0.46, and
`--text-dim`/`--text-faint` back to `ink-300`/`ink-400`. Deployed and
confirmed the revert landed clean. The actual fix — legibility via text
color rather than backdrop opacity — is still open; not yet designed.

## 2026-08-03 — the real fix: low fixed opacity, plus a bug nobody had found

Designed the text-color approach: opacity on `.sidebar`/`.card`/`.main`/
`.kiosk-*`/`.empty` dropped to a low, constant 0.2-0.3 (theme-tinted, not
daypart-tinted) purely as a frosted-glass effect, sharing a new `--pane-rgb`
variable. Legibility moved entirely to `--text`/`--text-dim`/`--text-faint`,
first keyed to both `data-theme` and `data-daypart` (eight combinations,
reasoned from the compositing math) before any of it touched real pixels.

Screenshotting that first version on the live Pi surfaced something the
math had missed entirely: the Home dashboard's tiles were *never* using any
of this. `.dash-tile` is built by `dashboard.js` (`Dash.add()`), not the
template, and never carried `class="card"` — so it had been sitting on a
flat, opaque `var(--bg-raised)` from `dashboard.css` since the "Almanac"
background was first introduced, regardless of anything tuned in
`nh-scene.css` across this entire multi-day thread. The Displays page
(plain `.card` divs, no dash-tile) always looked right; the actual
most-viewed page in the house never did. Fixed by giving `.dash-tile` the
same `--pane-rgb` glass treatment as `.card`.

With the tiles actually translucent, re-screenshotted all eight
(theme, daypart) pairs for real and three didn't match the predicted
bucket — dark theme at noon and dawn, light theme at night — all three
landing in a medium-brightness zone the compositing math called wrong.
Rather than patch three cells, re-derived the rule from the screenshots
themselves: at this low, fixed opacity the *theme's own tint* dominates
every daypart — dark theme's near-black glass never gets bright enough to
need dark text, light theme's near-white glass never gets dark enough to
need light text. Daypart doesn't matter for text color at all; simplified
from eight rules to two. Verified the full grid again after the
simplification — all eight combinations legible, atmosphere visible
throughout, no opacity increase anywhere.

## 2026-08-03 — sidebar simplified: Habits and Tracker out of nav, House/System/You merged

Three requested nav changes, done together:

- **Habits gone.** `houseapps.example_habit` (the reference app used throughout
  `DEVELOPMENT.md`'s onboarding flow) is no longer part of this house's running
  app set. Disabled the same way `uninstall_app`'s default mode does —
  non-destructively, via `NORA_HOME_HOUSE_APPS=` in the Pi's `.env` — code and
  any data stay on disk; `install_app` would bring it back exactly as it was.
- **House, System, and the hardcoded "This house" block collapsed into one
  "House" group.** Assistant and Measurements moved from `Category.SYSTEM` to
  `Category.HOUSE` so they land in the same nav-registry loop iteration as
  Displays; Apps/Status/Settings now render inside that same group's div
  instead of a separate "This house" header. Notifications' category moved
  too, only so it doesn't leave a stray empty "System" header behind — it
  still renders manually as "Alerts" above the loop, unchanged.
- **Tracker dropped from nav** (`nora_nav = False`). The app itself and the
  Today/Overdue/Reliability cards it powers on the Home dashboard are
  unaffected — only the standalone nav link is gone.
- **"You" and "Settings" merged into one page.** `core:settings` now also
  renders the member profile and escalation-chain cards that used to live at
  `accounts:profile`, which just redirects there now. One nav link instead
  of two.

Two real bugs found deploying this, both fixed in the same pass:

- **`env_list()` silently ignored an explicitly empty override.** It read
  through the shared `env()` helper, which treats `""` the same as "not set"
  — correct for scalars (an accidentally-blank secret shouldn't vanish
  silently) but wrong for a list, where an explicit empty value is a real,
  meaningful config. `NORA_HOME_HOUSE_APPS=` (the exact line both my manual
  edit and `uninstall_app` itself would write after removing the only house
  app) was falling back to the default `["houseapps.example_habit"]` instead
  of actually being empty — so the documented uninstall workflow would have
  silently un-done itself on every restart, for anyone, not just this
  session. `env_list()` now checks `os.environ` presence directly instead of
  going through `env()`'s scalar-oriented fallback.
- **Another multi-line `{# #}` template comment rendered as visible text** in
  the new House nav-group markup — the exact bug class already documented in
  this log from 2026-07-31, missed again writing new code. Fixed with
  `{% comment %}`.

Verified on the live Pi with Playwright: the sidebar now reads Home, Alerts,
House (Displays/Assistant/Measurements/Apps/Status/Settings), Integrations —
no Self Improvement, no Tracker, no separate This house/You — and
`/home/settings/` shows the profile card, escalation chain card, and wall
schedule card together on one page.

## 2026-08-03 — Assistant out of nav (Story 13), and the Apps directory stopped linking to fiction

**Assistant pulled from the sidebar**, same treatment as Tracker last round
(`nora_nav = False` on `AIConfig`) — code, models, and the console stay
installed, nothing deleted. Story 13 ("AI — Claude Integration") already
existed on the dashboard at exactly the right status, "partial/unproven,"
since no API key has ever been available to actually test it against; that
story is now the single place tracking this feature, with a note added
about the nav removal so re-enabling it later is a deliberate, tracked
decision rather than something that quietly crept back.

**Asked to make the Apps directory only show apps that are actually there.**
Investigated `registered_apps()`'s output directly rather than guessing, and
found real, concrete breakage: `ui` and `datastores` have no `urls.py` at
all, so their listed URLs (`/home/`, `/home/system/`) were pure fiction —
clicking "Interface" landed on the Home dashboard by coincidence (same
prefix as `core`), and clicking "Data" landed on the Status page (same
prefix as `core`'s `system/` route) — two different apps quietly aliasing
someone else's page. `dashboard` had a `urls.py`, but its own `""` route
renders the identical view as `core`'s `/home/`, so it was really just Home
under a second name. `mcpserver`'s two real endpoints both require MCP
device-token auth, not the session login every other row assumes, so a
human clicking "MCP" got a bare `{"error": "unauthorized"}`, not a page.

Added `nora_has_page` to `NoraAppConfig` (default `True`) and set it `False`
on exactly those four (`ui`, `datastores`, `dashboard`, `mcpserver`) —
they're still real, installed, legitimate parts of the platform, just not
things a person can visit, so the directory view now filters on
`has_page`. Two more had real pages just at the wrong URL, fixed rather
than hidden: `accounts` ("Household") pointed at bare `/accounts/`, which
has no index route — repointed at `/accounts/household/`, its actual page.

Verified locally: `registered_apps()` now shows `has_page=False` on exactly
those four, `has_page=True` and a working URL on everything else, and
`manage.py check` clean.

**Same session, one more layer of this.** Shown a screenshot of the fixed
Apps directory, pushed back further: it was still listing Displays, Alerts,
Assistant, Measurements, Integrations, Tracker, and Home as if they were
"apps" — but every one of those is an internal Django app that's part of
the platform itself, not something a family member installed. The registry
already drew this exact line — `house_apps()`, "apps the family wrote, as
opposed to platform apps" — the page just never used it, using
`registered_apps()` (everything) instead.

`core:app_directory` now calls `house_apps(include_disabled=True)` (added
`include_disabled` to `house_apps()` for parity with `registered_apps()`),
and the template got a real empty state instead of an empty table when
there's nothing to show — accurate right now, since Habits was the only
family app and it was removed a session ago. Points at `DEVELOPMENT.md`'s
"Ten-minute start" for how to add one. Verified on the live Pi: the page
now genuinely reads as "nothing installed yet," not a broken or incomplete
table.

## 2026-08-03 — the home bot: now a robot, grounded, and just says "Hi"

Three requested changes to `nh-bot.js`/`nh-bot.css`, done together:

- **Look.** Rounded-square head instead of the organic blob shape, a small
  antenna with a glowing tip, a dark visor panel housing two LED-style eyes,
  and a flat mouth bar — reads as a robot rather than an orange smiley.
  Existing mood animations (thinking/proud/concerned/sleepy/celebrate) still
  target the same elements, unchanged.
- **Movement.** `moveTo()` no longer takes a vertical position at all —
  it's always computed internally as a fixed strip near the bottom of the
  screen; only the horizontal position varies, whether from idle wandering
  or sliding toward whatever was just clicked. This also retroactively
  fixes the bot-overlapping-the-heading bug spotted a couple of sessions
  back, since that could only happen when she was free to wander into the
  upper portion of the screen.
- **Click.** `onPoke()` now just says "Hi" — dropped the random greeting
  pool, the server poke round-trip, and the celebrate spin. Deliberately
  minimal; what she should actually do when poked is still open.

Verified on the live Pi: screenshotted the robot look and the "Hi" bubble,
and drove `NoraHome.wander()` six times in a row through the browser
console — x varied freely (466-1271px), y stayed at exactly 810px every
time.

## 2026-08-03 — the bot, round two: a real bug, and a Mars rover

Reported immediately after the robot redesign shipped: clicking a button
made it slide diagonally from top-left to bottom-right. Root-caused rather
than patched blind: this is a traditional multi-page Django app, so a
button that navigates reloads the whole page, and `nh-bot.js`'s `mount()`
runs fresh on every one of those loads. `.nh-bot` sits at its CSS default
(`left:0, top:0` — top-left) until the first `moveTo()` call sets a real
transform, and since `.nh-bot` always carries `transition: transform`,
*that first positioning animated too* — reading as a slide in from the
corner on every single navigation, not just once on initial page load.
Fixed by disabling the transition for that one call and forcing a layout
flush before turning it back on, so only genuine subsequent moves animate.

Separately, asked to make it look like a Mars rover instead of the robot
head from last round. Rebuilt `.nh-bot__body`'s contents as stacked pieces
— three wheels, a chassis, a thin mast, a camera head with two lensed
"eyes," a short antenna off one corner — instead of the single face-on-a-
blob shape. First pass had two real problems caught by zooming into an
actual screenshot rather than trusting the code: the antenna (drawn as an
angled dish off the mast) rendered as a stray floating ball, disconnected
from anything, because it was positioned relative to the mast instead of
the head it was meant to sit on; and the eye glow was strong enough to
blur the two lenses into a single oval at the icon's real 62px size.
Fixed by nesting the antenna inside `.nh-bot__head` (so it's unambiguously
part of the head) and reducing the glow radius on both the eyes and the
head panel. Re-screenshotted at 4x zoom to confirm before calling it done.

## 2026-08-03 — Add a widget was broken by the bot's own script, silently

Reported as "Add a widget functionality is not working." Root-caused with a
real request, not a guess: `window.NoraHome.csrfToken` was `undefined`.
`nh-bot.js` ended with `window.NoraHome = NoraHome` — an unconditional
overwrite of the global object `nh-app.js` (loaded first, per `base.html`)
had already put `post()`/`csrfToken()` on. Every page with the bot enabled
silently lost both the moment nh-bot.js ran.

`dashboard.js`'s `Dash.save()` needs `csrfToken()` for its CSRF header;
without it the save POST came back `403`. Confirmed directly: called the
save endpoint from the console with the token nh-bot.js's overwrite left in
place — `403`, empty token. `fetch()` only rejects on a network failure,
not a non-2xx status, so that `403` resolved fine and `Dash.add()`'s
`.then(reload)` fired anyway — the picker closed, the page reloaded, and
the widget was never actually persisted. Looked exactly like "nothing
happens" from the UI, with no error visible anywhere.

Fixed at the source: `nh-bot.js` now extends the same `window.NoraHome`
object `nh-app.js` created (`window.NoraHome = window.NoraHome || {}`)
instead of replacing it. Also hardened `Dash.save()` to check
`response.ok` and throw on failure rather than treating any resolved fetch
as success, so a real failure now shows the existing "I couldn't save that
layout" message instead of silently reloading with nothing saved.

Verified live on the Pi, not just read: confirmed `csrfToken`/`post`/`say`
are all functions on `window.NoraHome` after the fix, then drove the real
UI — opened the picker, added "Disk," and confirmed the tile count went
from 5 to 6 *after a reload* (persisted server-side, not just added to the
in-memory list) — then removed it again the same way to leave the
dashboard as it was.

## 2026-08-04 — docs restructured, and three dead things found behind the "stale buttons"

A batch of documentation work, plus a UI fix — and the documentation pass turned
up real dead code, which is the point of doing it.

### The dropdown

The profile menu is a native `<details>`, which only closes on a second click of
its own `<summary>`. Added `wireProfileMenu()` in `nh-app.js` to close any open
`.profile-menu` on a click outside it, which is what every other dropdown on the
web does.

### "Remove the stale buttons from the 10.1 display" — bigger than it looked

The kiosk footer had **Dim** and **Wake**, sending `sleep` / `wake`. Checked
`wall-live.js` rather than assuming: it implements `navigate` and `refresh` and
nothing else. Both buttons had been doing literally nothing since the wall was
rebuilt around an iframe. Screen power is a host-side concern anyway
(`xset dpms` on a systemd timer, set from Settings), not a socket message.

Tracing why they were dead surfaced two more things:

- **The 24" wall had silently stopped showing alerts.** `display` is a real
  notification channel — `notifications/channels/display.py` sends
  `{"type": "banner", ...}` — and the old ambient `wall.js` rendered it. The
  replacement `wall-live.js` never had a `banner` case and `wall_live.html` had no
  banner element, so every alert routed to the wall was accepted by the bus and
  dropped in the browser. The `.wall-banner` CSS was still sitting there unused.
  Restored both.
- **`rotate_wall_display` was still running every 45 seconds, forever.** It sent
  `next` to advance the old panel rotation; the iframe wall has no `next` handler.
  It was waking the Celery worker on a timer to send a message nothing listened
  for. Removed the task and its beat entry.

Also trimmed `KIOSK_ACTIONS` from ten actions to the three the wall actually
implements, and removed the **Showing** and **Rotation** rows from the Displays
page — both were rendering panel-rotation state that stopped meaning anything when
the wall changed.

**The pattern worth remembering:** the display bus relays anything, and the browser
silently ignores what it has no handler for. A control wired to an unimplemented
message type looks completely functional. Adding a message type means adding its
handler in the same commit — this has now bitten twice.

### docs/ restructured

Reorganised by **who the document is for**, replacing a flat folder:

```
docs/User/         deployment.html, dashboard/ — people, not agents
docs/Main_App/     DEVELOPMENT, cross-functionality, architecture, testing,
                   progress, + subsystems/ (one file per platform subsystem)
docs/House_Apps/   one folder per family app, holding that app's docs
```

New in this pass:

- **`Main_App/cross-functionality.md`** — the index of every published cross-app
  API, with signatures copied from the code rather than from memory: tracker,
  notifications, telemetry, widgets, displays, AI, datastores, MCP, signals. Ends
  with the rule about calling the spine directly and never importing a peer app.
- **`Main_App/testing.md`** — how to verify work on the real hardware: Pi access,
  the deploy loop, Playwright recipes, `scrot` on the physical screens, and an
  explicit table of what this *cannot* catch. Records the Pi's SSH details on
  purpose so an agent can check its own work without asking; there is no secret in
  them (a private LAN address, a username, and the path to a key that stays on the
  dev machine).
- **`Main_App/subsystems/*.md`** — twelve files, one per platform app, each with
  the same headings a house app uses. The *Known gaps* sections are the honest
  ones: telemetry has exactly one series in this house, AI has never made a single
  request, no backup has ever been restored.
- **`House_Apps/`** — one folder per app. `install_app` now checks for
  `docs/House_Apps/<name>/README.md` and warns when it is missing, so "required" is
  enforced rather than merely stated. `example_habit/README.md` is the template.

Deleted `capabilities.html` (and its `core:capabilities` route and view) and
`design-options.html` — the first was an unmaintained parallel description of the
platform, the second was mockups for a design decision made months ago.

`DEVELOPMENT.md` gained a **five surfaces** section covering the 24" wall, the
10.1" kiosk, phone, tablet and desktop — what `data-surface` each gets, how it is
detected, what to design for, and the PWA/no-build constraints. Its checklist and
Ten-minute start now include writing the app's docs.

`CLAUDE.md` § 0 was rewritten around the new layout. It stays at the repo root
deliberately — it is auto-loaded from there, and moving it into `docs/` would stop
it being read.

Verified: `manage.py check` clean, and a link-checker walked every markdown file
including `CLAUDE.md` — all relative links resolve.

## 2026-08-04 — Displays folded into Settings; window controls answered with a no

Asked to move Displays into Settings and drop its nav tab, remove the duplicate
kiosk link, and add **Minimize** and **Close** next to each screen's Open button
— "if not possible, tell me."

Done: the two screen cards now sit on the Settings page directly above the wall
power schedule that configures them, `/home/displays/` redirects there so
bookmarks land, and `DisplaysConfig` is `nora_nav = False`. The wall and kiosk
pages themselves are untouched — they are what the physical screens load.
`templates/displays/manage.html` deleted.

The redundant "Kiosk / Open the kiosk controller" heading and button went too: the
kiosk already had its own card with an Open button, so it was the same link twice.
Fixed a latent bug in the process — a shared Open button would have sent the kiosk
card to `wall_named` with the kiosk's slug, rendering a *wall view of the kiosk*.
The card now branches on `display.kind`.

**Minimize / Close: not possible, and worth writing down why.** Two separate
walls, neither of them a matter of effort:

1. *In the browser you are holding* — there is no JavaScript API to minimize a
   window at all, and `window.close()` only works on windows a script opened
   itself. So these cannot be real buttons for the current tab.
2. *For the physical screens* — Django runs in Docker. Checked
   `docker-compose.yml` directly rather than assuming: the `web` service has no
   `DISPLAY`, no `/tmp/.X11-unix` mount, no host networking, no `privileged`. It
   cannot see the Pi's X session, so it cannot touch the wall's or kiosk's
   Chromium windows.

The only bridge that exists runs the other way and polls: `~/.nora/wall-power.sh`
calls `manage.py wall_power_state` on a 5-minute systemd timer and acts with
`xset`. Window controls would need that same shape — a host-side agent polling for
intent, at a few seconds rather than five minutes to feel like a button, plus
`xdotool windowminimize` / `wmctrl -c`. That is a new permanently-running daemon
on the Pi, so it was raised as a question rather than built unasked. Recorded in
`subsystems/displays.md` § Known gaps.

Verified on the Pi: sidebar no longer lists Displays, `/home/displays/` redirects
to `/home/settings/`, both screen cards render online with correct Open targets
(`/home/displays/kiosk/` and `/home/displays/wall/wall/`), and `manage.py check`
is clean.

## 2026-08-04 — Settings redesigned as grouped rows

"What's this boxes of varying sizes, it just looks bad." Fair, and the cause was
structural rather than cosmetic: the page was a `.card-grid`
(`auto-fill, minmax(280px, 1fr)`) holding five panels whose content lengths had
nothing in common — a seven-row profile card beside a two-line escalation card
beside a three-input form, then two screen cards orphaned onto a second row.
Cards of unequal height in an auto-fill grid always look ragged; no amount of
padding tuning fixes the arrangement. The global `input { width: 100% }` made it
worse, stretching both hour fields the full column width for a two-digit value.

Replaced with the pattern every OS settings screen already uses: one readable
column (max 780px), grouped sections, each setting a row with its label on the
left and its control on the right. Heights stop mattering because nothing sits
side by side, and it grows one row at a time without ever going ragged — which
is the stated plan for this page, since settings get added one at a time.

Three groups: **You** (profile, quiet hours, escalation chain, actions),
**Screens** (each screen's status and Open), **Overnight** (the power schedule).
New `.settings` / `.setting` classes in `nora-home.css`. The panel is a real
`.card`, so it keeps the glass material and inherits any future change to it
rather than forking the material. Rows collapse to one column under 620px so the
control sits under its label on a phone and on the kiosk.

Verified on the Pi: desktop renders as intended; the schedule form still saves
and persists across a reload (changed a value, confirmed, restored it); the
phone viewport stacks rows to a single column. One thing that looked like a bug
was not — a full-page screenshot showed white below the fold, which is just how
`position: fixed` backgrounds capture; scrolled to the bottom in a real viewport,
the living background covers the page correctly.

---

## 2026-08-04 — a test suite, written to be cheap to read

Asked for unit tests across the whole app, recorded in `testing.md`, with the
same expected of each house app — and specifically **written so they run on the
Pi and report pass/fail compactly, to reduce token usage**. That last constraint
shaped the design more than the tests themselves did.

### The report is the feature

Raw pytest output is hundreds of lines, and an agent reading it back over SSH
pays for every one. So the root `conftest.py` replaces pytest's summary with a
fixed-size report: one line per subsystem, one line per failure carrying only
its assertion. A green run is ~20 lines however many tests there are. Full
tracebacks still exist — `scripts/run-tests.sh` writes them to
`logs/test-full.txt` — so the detail is one file read away instead of being paid
for on every run.

The reporter is built so it cannot report a false green. That mattered
immediately: the first version printed `ALL PASSED` on a run where a whole file
failed to import (a hyphen in a function name), because a collection error never
reaches a test's call phase and so was invisible to the per-test hooks. It now
reports `BROKEN` for collection errors and `NOT OK` for any other non-zero exit.
A report that is trusted without reading the raw output has to earn that.

### 496 tests, one file per subsystem

`tests/`, no containers, no network, no credentials — SQLite, in-memory channel
layer, eager Celery, ~2 seconds. Deliberately hermetic so it gives the same
answer on a laptop and on the Pi. `pytest` and `pytest-django` went into the
production image (`requirements/test.txt`) so `make test-pi` works on the machine
the house actually runs on; it still runs under `config.settings.dev` there, so
tests get their own SQLite database and never touch real MySQL data.

Coverage is per subsystem: registry, core, accounts, scheduling, escalation,
tracker, notifications, telemetry, displays, integrations, scene, dashboard, ui,
every page requested for real, and a contract file that walks *every* installed
house app.

**Verified in the built production image, not just on the laptop** — and that
caught a fourth bug. pytest-django's settings precedence is `--ds`, then the
`DJANGO_SETTINGS_MODULE` *environment variable*, then the ini file. The image
exports `DJANGO_SETTINGS_MODULE=config.settings.pi`, so `pyproject.toml`'s
setting lost, and all 496 tests errored trying to reach the real Redis and MySQL
the moment the suite ran inside a container. `run-tests.sh` now pins it with
`--ds`, which is the only level that beats the environment. The docs had
confidently claimed the opposite; running it in the image is what disproved
that. 496 green inside the image afterwards, on Python 3.13.

### Four things the suite found while being written

- **`notify_house()` accepted a `dedupe_key` and ignored it.** Only `notify()`
  checked for recent duplicates. Every caller that passes a key here is a
  repeating source — a threshold on a stuck sensor, an integration that keeps
  failing, a top-rung escalation — so each cycle put a fresh banner on the wall.
  Personal alerts were suppressed; house-wide ones, the loudest surface in the
  building, were not. Fixed, with a test naming the day it was found.
- **The suite caught its own flakiness before it could rot.** Two notification
  routing tests failed only because the run happened at 05:54, inside the
  default 22:00–07:00 quiet window, which silently reroutes every push channel
  to `inapp`. `make_member` now disables quiet hours by default; tests that are
  actually about quiet hours set the window themselves. A test that passes all
  day and fails at 22:00 is worse than no test.
- **`current_scene()` could 500 every screen at once.** It runs in a context
  processor on the first paint of every page, and read a `HouseSetting` that a
  person can edit in the admin. A non-dict value there — a string, a list —
  would raise on `.get()`. One bad edit would have taken down the wall, the
  kiosk, and every phone together. Now degrades to "no weather yet", which is
  what the module already promised.
- **The reference app teaches the pattern the platform forbids.** CLAUDE.md §6
  says never import another app's models; `example_habit` imports
  `nora_home.tracker.models` in five files, and it is the app DEVELOPMENT.md
  tells every family member to copy. Not fixed here — clearing it needs query
  helpers on `nora_home.tracker.api` that do not exist yet (streaks for a
  `source_ref`, completion history, the open occurrence for a record). Recorded
  as `KNOWN_MODEL_IMPORT_DEBT` in `tests/test_house_apps.py`, with a companion
  test that fails if the entry ever stops being true, so new apps are held to
  the rule while the debt stays visible rather than hidden.

### The house-app contract

`tests/test_house_apps.py` walks every installed app rather than naming any, so a
family member's new app is checked the moment it is installed: identity and
category, no reserved URL prefix, page returns 200, every declared widget/card/
wall panel loads, wall panels are `wall_safe`, kiosk control paths resolve, models
inherit `TimeStampedModel`, a migration exists, no `os.environ`, no cross-app
model imports, and both required docs present.

That last one is new: each house app now needs `docs/House_Apps/<app>/testing.md`
as well as its README. `install_app` warns for both; the contract test fails
without them. `example_habit/testing.md` is written as the template, and leads
with which checks the platform already runs so nobody writes them twice.

### One test worth calling out

`test_every_kiosk_action_has_a_handler_on_the_wall` parses `wall-live.js` for its
`case "..."` branches and asserts every action in `KIOSK_ACTIONS` has one. This
subsystem's recurring bug is not a crash but silence — the bus relays anything,
the browser ignores what it cannot handle, so a dead control looks alive. It has
happened twice (the kiosk's Dim/Wake buttons, and the notification banner). This
makes the third time fail in CI instead of on the wall.

---

## 2026-08-04 — the suite on real hardware, and what it flushed out

Running the new suite on the Pi, then cleaning the 10.1" kiosk and auditing for
dead code. Almost everything below was found by looking at the thing rather than
reading it.

### The suite on the Pi

428 of 496 tests failed the first time, for a reason no laptop run could show:
`config.settings.dev` is not hermetic. It layers on `base.py`, which reads the
database engine, cache, and installed house apps from `.env` — so on the Pi it
resolved to the real MySQL and tried to create `test_nora_home`, which the
`nora` user has no grant for. `config/settings/test.py` now pins all of it and
reads no environment at all. **536 passing on the Pi**, ~20s.

### Celery was never broken; the healthcheck was

`worker` and `beat` had shown `unhealthy` for days — CLAUDE.md §2 carried it as
an open question. Both inherit the Dockerfile's HEALTHCHECK, which curls
`localhost:8000`, the *web* role's port. Neither runs an HTTP server, so it could
never pass: a 473-long failing streak against a worker that pongs instantly.
Confirmed end to end instead — **279 health snapshots in the database, newest 5.5
minutes old**. All nine services now report healthy, for the first time.

The beat log did expose a real bug. `displays.rotate` was deleted from
`config/celery.py` on 2026-08-03, but beat runs django_celery_beat's
DatabaseScheduler, which syncs `beat_schedule` into the database and never
removes what was taken out of it. The row survived every rebuild; beat kept
dispatching it every 45 seconds and the worker logged `Received unregistered
task ... KeyError` each time, for a day and a half, silently.
`prune_beat_schedule` now runs before beat starts.

### The kiosk

Screenshotting the physical panel showed Dim/Wake, a Displays tile, Tracker, and
a duplicate Alerts — none of which the current code produces. The page was
simply stale; Chromium had not reloaded since those changes shipped. But three
real bugs were underneath it:

- **The HTTP fallback had never worked.** `kiosk.js` posted to
  `/displays/<slug>/command/`, missing the `/home/` prefix the platform is
  mounted under. That 404 is what put "Couldn't reach the wall display." on the
  panel.
- **And the endpoint was unreachable anyway.** Django resolves in order, so
  `/home/displays/wall/command/` matched `wall/<slug:slug>/` as
  `wall_named(slug="command")` — the command view could not be hit for the one
  display the kiosk targets. Now `command/<slug>/`, so the literal segment comes
  first and the ambiguity is gone rather than depending on line order. Worth
  noting the obvious test was not enough: the *old* URL resolves perfectly well,
  just to the wrong view, so the test asserts `url_name == "command"`.
- **`command` accepted seven actions the wall ignores** — show/pin/unpin/wake/
  sleep/next/previous, all from the ambient wall. Callers got `{"ok": true}` for
  nothing.

Plus the duplicate Alerts tile: one hardcoded in the view, one from the
notifications app's nav entry.

Verified after: kiosk shows 7 tiles and a two-button footer, no error toast, and
a simulated tap on Measurements moved the wall to that page with real telemetry
on it (22.2°C from the weather integration).

### Dead code audit

No TODOs, FIXMEs, or HACKs anywhere; no unreferenced templates or assets once
`wall.html`/`wall.js` went. The real find was the Display model. Keeping
`rotation_enabled` / `rotation_seconds` / `current_panel` "in case a passive view
is wanted again" was the trap, not the safety net — they kept admin columns and
a websocket connect payload alive reporting values nothing set and
`wall-live.js` had never read. `pinned_until`, `night_mode_start`/`_end` and
`brightness` went the same way, screen power having been host-side since the
Settings work. Migration `0002` drops all seven; the connect payload is now just
the slug. Git history is the archive.

Also removed: `_persist_show` (zero callers), `show_panel` (only that and the
dead command action), and `kiosk.js`'s `data-panel`/`markActive` branches.

### House apps now have a three-gate workflow

Written into DEVELOPMENT.md, CLAUDE.md §0, and `docs/House_Apps/README.md`, and
enforced by `install_app` and the contract tests:

1. **`requirements.md` first**, in plain language, **approved by the user before
   any code is written**. `example_habit/requirements.md` is the template.
2. **Development is not done until tested and integrated** — unit tests for the
   app's own logic, plus verified integration with tracker, notifications,
   telemetry, widgets, nav and kiosk, with the whole suite green.
3. **Deployed to the Pi and confirmed over SSH**, screens screenshotted. Until
   then the app is *built, unproven*, never Complete.

---

## 2026-08-04 — the reference app stops teaching the wrong thing, and Slack goes live

Asked whether the platform was ready for house apps. Rather than answer from the
code, copied the reference app into a scratch house app and ran the contract
tests against it — which is the path a family member's agent will actually walk.
It failed immediately on
`test_the_app_does_not_import_another_apps_models[plants]`.

That confirmed the debt recorded earlier was not cosmetic. `example_habit`
imported `nora_home.tracker.models` in five files, and it is the app
DEVELOPMENT.md tells everyone to copy — so **every new house app would have
started with a failing suite, on a rule the reference app itself broke.**

The rule was fine; the API was incomplete. `nora_home.tracker.api` now answers
what those files were reaching into models for:

| Function | For |
|---|---|
| `streak_for(app_slug, source_ref)` | Consecutive completions on your record |
| `is_done_today(app_slug, source_ref)` | What greys out a "done" button |
| `history_for(app_slug, source_ref, limit)` | A detail page or chart |
| `completion_stats(app_slug, members, since, until)` | `{done, missed, total, rate}` |
| `trackable_for(app_slug, source_ref)` | The escape hatch, read-only |

`completion_stats` returns `rate=None` rather than `0` when nothing was due — a
gap in a chart is honest, a zero says "you failed" when there was nothing to do —
and ignores still-pending work, so a week in progress does not read as a week
half-missed. `KNOWN_MODEL_IMPORT_DEBT` is now empty, with a comment saying that if
you are about to add an entry, add the API function instead. Re-ran the scratch
app afterwards: clean.

### Slack, end to end

A bot token was supplied. `auth.test` succeeds — team *Puffin Robotics*, bot
`nora_home`. Two environment traps before it got that far, both now documented in
`.env.example`:

- the token was **quoted** in `.env`, and Compose passes `env_file` values
  through literally, so the app saw a token starting with `"`;
- the container had not been recreated since the edit, so it saw an empty string.

Delivery still fails, and the remaining two blockers are in the Slack workspace
rather than in this code: the token carries only `commands`, `chat:write`,
`app_mentions:read` — posting to a channel the bot has not joined needs
`chat:write.public` (or an `/invite`), and the escalation ladder's DMs need
`im:write` — and no `HouseMember` has `slack_user_id` set.

Worth its own note: **Slack's error strings are accurate and useless.**
`channel_not_found` is what it returns both when the channel does not exist and
when the bot was simply never invited to it. A valid token, a live workspace, and
that bare string pointed at nothing. `SlackChannel` now maps the common codes to
the action that fixes them, keeping the raw code alongside.

### Also

Fixed two stale entries that claimed work was unverified after it had been
verified on the Pi — CLAUDE.md §2 item 7 (kiosk redesign and Settings) and the
matching note in testing.md.

557 tests, green on the laptop and on the Pi.

---

## 2026-08-04 — one runner, `./nora`

Operations were spread across `scripts/install-pi.sh`, a Makefile, and a pile of
remembered `docker compose` incantations. `./nora` is now the single entry point,
and its `help` is the one piece of documentation guaranteed to be in front of
whoever needs it: install, up, down, status, logs, restart, recreate, upgrade,
screens, backup, restore, app install/list/uninstall, member, token, test,
manage, shell, cert, uninstall.

The Pi provisioning is unchanged and still hardware-verified — it moved to
`scripts/lib/provision-pi.sh` and `nora install` runs it. It stays one linear
script rather than being folded into the runner, because the knowledge in it
(X11 over Wayland, the touchscreen transformation matrix, per-output Chromium
placement) was expensive to learn and is easier to read in order. The Makefile
survives as thin aliases that delegate, so there is one implementation.

Three things it encodes that were tribal knowledge until now:

- **`recreate`**, because editing `.env` and restarting does nothing — a running
  container keeps the environment it started with. That cost a session with the
  Slack token this week. The help text says so, and a test asserts the help text
  says so.
- **`upgrade` migrates explicitly** rather than leaning on the entrypoint, so a
  failed migration stops the upgrade instead of leaving a half-started house.
  It backs up first.
- **`screens` searches Chromium by window title, not class.** Class matches
  Chromium's helper windows and silently reloads nothing — which wasted a round
  trip earlier the same day.

Destructive commands back up and confirm before acting (`uninstall`, `app
uninstall`, `restore`), with `--yes` to skip deliberately.

### Two bugs, both found by running it rather than reading it

- **`upgrade` doubled the manage.py prefix.** `docker/entrypoint.sh` treats an
  unrecognised argument list as a management command and prepends
  `python manage.py` itself, so passing the full command line produced
  `manage.py python manage.py migrate`. Split into `manage_offline` (management
  commands) and `raw_offline` (anything else — `run-tests.sh` needs the
  entrypoint *out of the way*, not applied twice). The failure was clean: it had
  backed up, pulled and built, then stopped without restarting anything, which
  is exactly what the explicit migrate step is for.
- **A self-updating script cannot fix itself mid-run.** The `git pull` inside
  `upgrade` replaced `nora` itself, but bash had already parsed the old version
  — so the commit fixing the bug above could not be applied by the upgrade
  installing it. Worse, bash reads scripts incrementally, so rewriting one
  mid-execution can make it jump into the middle of a line. `upgrade` now
  compares the runner's blob hash across the pull and `exec`s the new copy to
  finish, guarded by `NORA_RESUMED` so it cannot loop or back up twice.

`tests/test_runner.py` guards the drift that actually bites — a dispatched
command with no function, a working command missing from `help`, a destructive
command that skips its backup, and any doc still telling someone to run the old
install script. Same shape as the kiosk-action test: something that looks wired
up and is not.

Verified on the Pi by running it: `status`, `backup` (a real archive),
`recreate`, `screens` (both browsers reloaded), `app list`, `test`, and a full
`upgrade` including the self-handover. 579 tests green there.

---

## 2026-08-04 — QA: a real browser, and what it found in four minutes

Asked whether the unit tests were QA. They are not: 579 tests that check Python
and never render a page, run a line of the 1,381 lines of shipped JavaScript, or
look at a pixel. Every user-visible bug in this project has lived in that gap
while the suite stayed green — "Add a widget" broken for a day, alert banners
never appearing, the kiosk showing deleted buttons, text nobody could read. The
QA layer was a person taking screenshots.

Then asked, fairly, why build it when open-source tools exist. That was the
better instinct and it changed the shape of the work: **most of the value is
off-the-shelf.** axe-core is somebody else's rule engine; console-error and
failed-request checks are a few lines of Playwright. Only the kiosk-drives-wall
flow is genuinely bespoke, because no tool knows this house has a 10" screen
that drives a 24" one.

`./nora qa` — 106 checks, ~4 minutes, from a laptop against the running house.

### Three findings on the first real run

- **A checkbox with no label.** The overnight schedule's toggle used a `<div>`,
  not a `<label for>`, so it had no accessible name and tapping its text did not
  toggle it — on a touchscreen that is the entire interaction. Mine, from the
  Settings redesign. Fixed.
- **The light theme is unreadable at dusk.** Near-black text on the evening sky,
  measured 2.06:1 against a floor of 3.0. Not a stray colour: `nh-scene.css`
  drives the sky from `data-daypart` alone with no `data-theme` branch, so three
  of the four dayparts are dark whatever the theme says. Anyone tapping "Theme"
  in the profile menu gets it. **Parked with a written explanation rather than
  quietly patched** — resolving it is a design decision about the Almanac
  direction (force a daylight sky, drop the living background in light mode, or
  drop the toggle), and that belongs to whoever owns the design.
- **axe's own contrast rule is unusable here** — and it took a pixel measurement
  to establish that rather than assume it. axe composites translucent panes onto
  the nearest opaque ancestor; this app paints a living gradient behind
  everything with `backdrop-filter` over it. So axe reported perfectly readable
  kiosk tiles at 1.95:1 against `#b4b5b6`, a grey that appears nowhere on screen.
  Measured from the rendering: 18:1.

That last one is the one worth remembering. **Believing the tool would have
meant "fixing" readable text and making it worse** — the same trap as the earlier
"reduce transparency" theory, and avoided the same way, by measuring what is
actually on screen. Contrast is now measured from screenshots, and the measurer
was validated by deliberately breaking a colour and confirming it caught it:
18.25 as shipped, 2.81 when broken.

### Four failures that were the tests' own fault

Worth recording because they are the standard traps:

- **`networkidle` never fires here.** The wall and kiosk hold a websocket open
  for their whole life and poll the weather, so the network is never idle. Every
  wait timed out after 30s, which is what made the first run take 5m25s and
  report failures that were nothing but a bad wait condition. `visit()` replaced
  it everywhere.
- **Page actions live inside the profile dropdown.** "Add a widget" is in the
  DOM but invisible until the menu is opened, so the click timed out. Not a bug —
  worth knowing before concluding a button is broken.
- **Already-added widgets render `disabled`**, so clicking the first item in the
  picker did nothing.

### Also

The reporter had a real gap: a skip raised inside a test body was invisible,
counted as neither pass nor skip — which would have let a deliberately parked
failure look like a pass. Now counted.

DEVELOPMENT.md tells house apps to write browser tests too, with the fixtures
they inherit and the `networkidle` warning, and gate 2 of the workflow now
requires `./nora qa` green as well as `./nora test`.

---

## 2026-08-04 — the light theme, fixed rather than parked

The QA suite's first run found the light theme unreadable and I parked it,
calling it a design decision. Told to implement the fix instead — correctly, it
was shipping and reachable from the profile menu, so "known broken" was not a
resting state.

Three separate causes, all found by measuring rather than by eye.

**The sky.** `nh-scene.css` drives it from `data-daypart` alone with no
`data-theme` branch, so three of the four dayparts are dark whatever the theme
says. And the page heading sits directly on the sky with no pane under it, so no
amount of pane tuning could ever have reached it — which is why the earlier
opacity experiments would not have helped here either.

The scene is now **veiled** in light mode rather than switched off or faked into
midday: season, weather, orb and horizon still read through, the way a landscape
reads through haze, but the ground under the text is light. That respects the
rule already written into that file and paid for by two earlier reverts —
legibility is not bought by hiding the scene.

**The veil value was measured, not chosen.** The first attempt used 0.86. It
passed contrast comfortably and washed the living background away almost
entirely — a plain light dashboard with no weather in it. Sweeping the value
against real rendered contrast:

| veil | dawn | noon | dusk | night | worst |
|---|---|---|---|---|---|
| 0.30 | 6.67 | 9.44 | 1.97 | 2.34 | **1.97** |
| 0.38 | 7.53 | 10.36 | 6.54 | 1.92 | **1.92** |
| 0.46 | 8.76 | 10.66 | 7.77 | 6.90 | 6.90 |
| 0.54 | 9.91 | 11.58 | 9.05 | 8.19 | 8.19 |
| 0.86 | 13.38 | 14.27 | 13.15 | 12.86 | 12.86 |

A sharp cliff between 0.38 and 0.46, and a wide safe shelf above it. 0.54 buys
most of the scene back while leaving the worst case at nearly double the 4.5
floor. Neither the cliff nor the headroom was visible by eye.

**The brand.** "Nora Home" is a bare `<a>`, so it inherited the apricot accent —
fine on dark glass, 2.13:1 in the light theme and 3.81:1 over the noon sky. It is
text, so it now uses `--text`, which already tracks the theme. The apricot
identity is carried by `.brand-mark` beside it, which is decorative and needs no
contrast. That one fix cleared a failure in *both* themes.

**The accent as a link colour.** Tuned for dark glass and never checked against
light: 1.93:1. The light theme now deepens the same hue to 5.1:1. `--nh-500`
itself is untouched, so the brand mark, chart series and glow keep their warmth.

All 32 theme x daypart x element combinations now measure 6.30:1 or better.

### And then the kiosk, found by running the suite an hour later

The run that confirmed the light theme was green. The next run, an hour on, was
not — `.kiosk-tile__hint` at 1.94:1. Nothing had changed but the sky: the check
had been passing against the night sky (7.79:1) and failed the moment the real
daypart moved to noon.

Two real problems under it, both the same oversight in different clothes. The
comment in `nh-scene.css` claiming the daypart does not matter — that the glass's
own tint dominates — was verified against `--text`, which is near-white and has
enormous headroom. It was never checked against `--text-faint`, a soft grey
chosen to recede, which is exactly the token the kiosk uses for the line telling
you which app a button belongs to. Promoted to `--text-dim`; on that surface it
is a label, not decoration.

That was not enough. At noon the sky's lower half is nearly white, so a 0.30
pane over it composites light and the tile *titles* then failed too (3.65:1) —
and no text colour fixes that without inverting the dark theme at midday. So the
kiosk's glass is now thicker than the app's (0.52 against 0.30), the one place
this file deliberately breaks its own rule. Scoped there because the kiosk is
not the ambient screen: the 24" wall carries the atmosphere, the 10.1" panel is
a remote control on a hallway wall, and a button you cannot read is a broken
button. Swept again — 0.42 leaves the worst case at 4.83, too close to the floor
to trust across seasons and weather; 0.52 puts it at 6.17 and still reads as
glass rather than a slab.

**The test was then pinned to every daypart**, because the failure had been
invisible for a whole run purely by the hour it was run at. A check on a surface
whose background changes all day has to pin the background — otherwise it is a
test that passes six hours out of twenty-four.

Worst case anywhere on the kiosk, any theme, any hour: 6.17:1. QA is 117 green
with no skips. The method — sweep the value, print the table — is written up in
testing.md, because it turns a taste argument into something checkable.

---

## 2026-08-05 — Todo designed: it replaces the tracker, and Levels replaces the
## "platform never depends on an app" rule

A long design session, no code. Asked for a Todo app; what it turned into is the
subsystem that **replaces `nora_home.tracker` entirely** — for the base app, for
house apps, and for the family.

Two decisions worth not re-litigating:

**Levels.** The old rule — the platform never depends on a house app — is
withdrawn. Level 1 is the base, Level 2 is what the base leans on (Todo), Level 3
is family apps that uninstall freely. What is now forbidden is a dependency
pointing *downward*: nothing at Level 1 or 2 may import Level 3. Needs
`nora_level` on the app config plus a directional test, or it decays into a
convention nobody enforces.

**Todo absorbs the tracker rather than sitting beside it.** The tracker is an
engine with no cockpit — `nora_nav = False`, four headless widgets, no page. Its
scheduling and escalation code is good and carries over; its model and surfaces
do not. `nora_home.tracker.api` becomes `nora_home.todo.api`, a clean cut with no
shim since the only caller was `example_habit`, which is being deleted anyway.

Three findings from reading the code during the design, all of them things that
would have been discovered mid-build:

- **`nora_wall_panels` is dead code.** The registry still collects wall panels and
  offers `wall_panels()`, and a contract test still validates them — but nothing
  has rendered one since the wall was repointed at the live app. The only two
  declarers are the tracker and `example_habit`. Deleted as part of this work.
- **`DashboardLayout.Surface.WALL` exists and is unused** — the same situation
  `SHARED` was in before the Everyone view adopted it. That is what makes "the
  wall is a widget collection the user picks" a small change rather than a new
  subsystem.
- **The audit log has four call sites and three are being deleted.** The
  mechanism (`core.audit.record()`) is good; the habit of calling it does not
  exist. A House log page and audit coverage have to ship together, or the page
  renders an empty table.

Also settled: Slack interactivity needs **Socket Mode**, not webhooks — the Pi is
behind home NAT with a self-signed cert, so Slack can never reach it, and no scope
changes that. Socket Mode dials outbound instead. Costs one small container.

And the scheduling recommendations ("you added an exam, move these three") are
**arithmetic, not AI** — deterministic, offline, free, and explainable, which is
what a system that reshuffles someone's week has to be. AI is designed for as a
judgement layer on top, and explicitly not built now; what is built now is the
data discipline that makes adding it later cheap — changes recorded as dated
events rather than counters, and every statistic computed from history on read.

Design: `docs/Main_App/subsystems/todo.md`. Build order:
`docs/Main_App/subsystems/todo-build-brief.md` (delete when built). Surface
mockups for all four screens: `todo-mockups.html`.

Broken into **Stories 28-41** on the dashboard as Phase 7, one per build phase,
each carrying its model and effort level. Roughly 70% Sonnet; Opus on 30
(recurrence — the correctness core), 35 (analytics), 37 (Slack Socket Mode) and
40 (tracker removal). Stories 5 and 6 are annotated as superseded-but-still-live
rather than retired, since the tracker keeps running until Story 40 deletes it.

---

## 2026-08-05 — Story 28: Levels, and clearing the ground for Todo

First story of the Todo build (Phase 7). Introduced `nora_level` on
`NoraAppConfig` (every platform `apps.py` now declares `nora_level = 1`
explicitly; the default of 3 covers house apps without them needing to say
anything), and a new test — `test_level_1_or_2_never_imports_a_level_3_app` —
that walks every registered app's source with `ast`, not just house apps, and
fails if anything at Level 1 or 2 imports a Level 3 module. It holds clean
today with zero exceptions. `uninstall_app` now refuses with a named
explanation ("this is a Level 2 app the base depends on, removing it would
break...") instead of the generic "not in NORA_HOME_HOUSE_APPS" it would
otherwise fail with.

Also deleted `houseapps/example_habit` entirely, and its usage in
`bootstrap_home.py`'s demo seeding — the platform now legitimately runs with
zero house apps installed until Story 24.

One deliberate scope decision, found by actually trying to widen the existing
"never import another app's models" test to cover platform apps rather than
just house apps: doing so would have surfaced real, pre-existing debt
unrelated to Levels — `bootstrap_home.py` and `mcpserver/tools.py` both import
`nora_home.tracker.models` directly instead of going through `.api`. Cleaning
that up is its own piece of work. The new Levels test was kept separate and
narrowly scoped to the one invariant Levels actually requires, rather than
quietly expanding to fix unrelated debt mid-story.

Zero-house-apps also broke three tests that had hardcoded assumptions about
`example_habit` existing (`test_reference_house_app_is_registered`,
`test_house_apps_mount_at_the_url_root`, `test_the_apps_page_lists_only_the_familys_apps`)
and one that used to guard against a silently-empty registry
(`test_at_least_one_house_app_is_installed`) — all fixed to treat zero house
apps as the legitimate current state (skip with a reason) rather than a
failure, since that guard's original purpose — catching an *accidentally*
empty registry — is a different thing from the registry being *deliberately*
empty right now. `test_house_apps_mount_at_the_url_root` also stopped
hardcoding the `habits/` slug and now checks whatever house apps actually are
installed, so it won't need editing again when Story 24 adds a real one.

Also removed `nora_wall_panels` — the field, the `wall_panels()` function
(confirmed zero callers before deleting), the contract test, and the dead
declaration on `nora_home/tracker/apps.py`. And fixed three user-facing
places still pointing at the deleted reference app that a pure code review
would have missed: `install_app`'s own warning messages, the Apps directory's
empty-state text, and `houseapps/__init__.py`'s docstring.

`./scripts/run-tests.sh`: 557 passed, 0 failed, 21 skipped (19 are pytest's
own empty-parametrize placeholders — expected and harmless until Story 24).
`manage.py check`: clean. No migration needed (no model changes this story).

Design: `docs/Main_App/subsystems/todo.md`. Build order:
`docs/Main_App/subsystems/todo-build-brief.md`.

---

## 2026-08-05 — Story 29: Todo's ten models

Second story of the Todo build. `nora_home/todo/` now exists with `apps.py`,
`models.py`, `admin.py`, and `migrations/0001_initial.py`, registered in
`NORA_HOME_PLATFORM_APPS`. Ten models, matching todo.md §3 field-for-field:
Task, Instance, Event, Label, Comment, Attachment, Link, Reminder, ChangeEvent,
TodoPreference.

Verified beyond the brief's stated bar (migration applies, `manage.py check`
clean) — every model was actually exercised against the ORM directly, not just
schema-deployed: created a Task without a priority and confirmed it's rejected
at the database level (no default, as designed); confirmed `Instance.clean()`
rejects a `skipped_at` set after `due_at`; confirmed every "exactly one parent"
CheckConstraint on Comment (task-or-instance), Attachment (task-or-instance-or-
event), Link, and Reminder actually rejects both-set and neither-set inputs at
the database level, not only in application code; confirmed `TodoPreference`'s
two fields (`default_due_hour`, `tone`) take the right defaults; confirmed
`Task.escalation_policy`'s string-reference FK into `tracker.EscalationPolicy`
resolves and round-trips correctly with no Python-level import of tracker's
models anywhere in the file.

Two places where the approved design doc was ambiguous or self-contradictory,
resolved and documented directly in the model code rather than guessed at
silently:

- §3 scopes Comment/Attachment/Link to "attach to either a task or an
  instance," but Event's own description separately lists "attachments" as
  something it holds, with no other model designated to carry them.
  `Attachment` was extended to a three-way task/instance/event parent to
  resolve this; `Comment` and `Link` were left at task/instance only, since
  Event doesn't claim to need those.
- Phase 1 of the build brief calls for copying `tracker/escalation.py` into
  the new package now (its item 1.3) — but §3's own field list for `Instance`
  has no escalation bookkeeping fields (no `escalation_level`,
  `last_escalated_at`, `acknowledged_at` equivalent) for that copied logic to
  operate on. Copying it now would produce code that imports cleanly but
  cannot actually run. Deferred to Story 30, where Instance's full shape gets
  settled as part of "Recurrence & Instances" — the more honest reading of
  where that work belongs, rather than a literal same-story copy that
  contradicts "no half-finished implementations."

`./scripts/run-tests.sh`: 557 passed, 0 failed, 21 skipped — no regressions.
`manage.py check`: clean. `makemigrations --check --dry-run`: clean.

Design: `docs/Main_App/subsystems/todo.md`. Build order:
`docs/Main_App/subsystems/todo-build-brief.md`.

---

## 2026-08-05 — Story 30: recurrence, materialisation, and how an occasion closes

The correctness core. `nora_home/todo/recurrence.py` evaluates the two kinds of
rule, `scheduling.py` materialises them into Instance rows, and two Celery jobs
(`todo.extend-windows` nightly, `todo.close-passed` every 5 minutes) keep the
board moving on its own. 51 tests for this story; 614 green overall.

**The missed rule is derived, not stored**, and that turned out to be the
design decision that made everything else fall into place. An instance is
missed once a *later instance of the same task is already due* — its turn is
over because the next turn has arrived. No `window_ends_at` column to keep in
sync when a rule changes, and the right answer for all three kinds drops out of
the one sentence: a daily task skipped for a week closes six and leaves today's
current (exactly §5's "the board does not grow seven cards"); a one-shot task
never has a later sibling, so an overdue todo sits on the board overdue rather
than quietly becoming history, which is what a person expects of "buy grout"
three months later; a rolling task only ever holds one open instance, so it
stays put until actually done.

**History is never backfilled.** A task created today whose rule anchors weeks
ago must not conjure a fortnight of occasions nobody could have done —
`close_passed` would immediately close every one as missed and invent a failure
that never happened. Instances exist only from the moment the task did. This
was not written down anywhere before; it is now, in the code and in a test.

Instance also gained the escalation bookkeeping fields (`escalation_level`,
`last_escalated_at`, `acknowledged_at`, `acknowledged_by`) that Story 29
deferred here. Written by nothing and read by nothing until the escalation
engine arrives with the notification routing it depends on — but the ladder
walks per-occasion, so this is where that state has to live, and settling it
now avoids touching Instance a third time.

**Two real bugs found during the build**, worth recording because of how
differently they surfaced:

- An interval of 0 days silently became "every day". `spec.get("days") or 1`
  treats 0 as absent, so the guard that was supposed to reject it never ran.
  Caught by a parametrised test that deliberately fed in nonsense specs.
- **Changing a task's due time wiped all 90 future instances and created
  none.** Filling the horizon before clearing stale rows meant the scan's
  starting point was computed from an instance that was about to be deleted:
  nothing new was created, then every future occasion was dropped as stale,
  leaving the board, the calendar and every reminder empty until the next
  nightly run. This one had no failing test — the suite was fully green. It was
  found by stopping to trace what actually happens when someone edits a due
  time, then confirming it against the real ORM. Fixed by clearing first and
  scanning from what survived; both now have regression tests.

Design: `docs/Main_App/subsystems/todo.md`. Build order:
`docs/Main_App/subsystems/todo-build-brief.md`.

---

## 2026-08-05 — Shared tasks and approval added to the design (Story 42)

Requested after Stories 29 and 30 had already shipped, so it lands as a
follow-up migration rather than a change to the original models. Recorded in
todo.md §4a and as Phase 2a of the build brief; **built between Stories 30 and
31**, not in number order, because the board renders it and building the board
against the single-owner model would mean building it twice. Numbered 42 rather
than inserted as 31 so the existing references in this log stay true.

The shape, after the five questions that needed answering:

- **`owner` survives alongside `assignees`.** Owner is who is *responsible*
  and who escalation chases — keeping exactly one person there is what stops
  the ladder becoming a group message nobody owns. Assignees are who *can do
  it*, and any one of them closes it.
- **An `approver` being set *is* the approval requirement.** The first sketch
  had a separate `completion_mode` flag; the answer that "one person works on
  it and if there is an approver, the approver approves it" removed the need
  for one. Fewer states, nothing to keep in sync.
- **Recurring tasks cannot have an approver**, enforced at the model *and*
  database level rather than left as a convention. Every occurrence of a daily
  task needing sign-off would be an approval queue nobody keeps up with, and
  the first week of it would teach everyone to rubber-stamp.
- **Rejection returns the task to open and the reason is required.** Stored as
  a `ChangeEvent` (`field="approval"`), so it needs no new table and lands in
  the same history as every other change.
- **Effort splits across assignees, never multiplies.** A 60-minute task shared
  by three contributes 20 minutes to each person's load. Counting it in full
  three times would tell three people they each have a full day of what is
  really one hour of house work — and Story 35's scheduling suggestions are
  built directly on that number, so the distortion would propagate into advice.

One thing that fell out for free: `/todo-approve` was already in Story 37's
Slack plan, speculatively. It now has a real meaning — approving or rejecting
from a phone, reason and all.

Stories 31, 32, 35 and 37 updated with the knock-on effects.

---

### 2026-08-05 — Story 42: shared tasks and approval

Built the design recorded earlier the same day. `nora_home/todo/api.py` is new —
Todo's first published surface, holding one occasion's journey through its
outcomes plus the two things sharing a task changes for everyone else. Migration
`0003`: `Task.assignees`, `Task.approver`, `Instance.approved_at/approved_by`,
`awaiting_approval` added to the outcome choices, and the
`todo_no_approver_on_recurring` check constraint. **42 new tests, 656 green.**

Three decisions the design had left open, settled by writing it:

- **`tasks_for()` excludes soft-deleted tasks and keeps archived ones.**
  `Task.objects` does no filtering of its own — `SoftDeleteModel` puts `.alive()`
  behind an explicit call — so every board would have shown deleted tasks unless
  it remembered. Archived stays visible, because "not now" is a column on the
  board, not a deletion.
- **Rejection keeps `note` and `actual_minutes`, clears `completed_at` and
  `completed_by`.** Deleting what someone typed because a third party said no is
  exactly the resentment §4a exists to avoid; but leaving `completed_at` set on a
  row that is `pending` again is a lie some later query will trip over.
- **`item_completed` fires once, on the transition into done** — not on
  submission for approval, and not when someone amends an occasion that was
  already finished.

**Two problems found by tracing rather than by a failing test**, which is the
lesson Story 30 had already taught in this subsystem:

- An occasion waiting on its approver has no `pending` row. `_materialize_one_shot`
  looks for exactly that to decide whether a task needs an instance — so the
  nightly job had to be checked for whether it would read "no pending instance"
  as "this task has never had one" and create a second card the doer would have
  to finish twice. It does not (it falls through to an `instances.exists()`
  check), but nothing had ever exercised that path, so there is now a test that
  does.
- `complete()` treated an amendment as a fresh completion. Correcting last
  week's note is a legitimate retroactive edit (§4), but it re-fired
  `item_completed` — Slack congratulating someone a second time for work they
  finished days ago — *and* restamped `completed_at`/`completed_by` to now and
  whoever was doing the correcting. The second half is the worse one: the
  history every chart is drawn from would drift a little further from the truth
  with each edit, silently. An amendment now leaves both alone and announces
  nothing; `at=` remains the way to genuinely correct a completion time.

Not yet run on the Pi: the migration alters an indexed column and adds a CHECK
constraint, and MySQL is not SQLite about either.

Next: **Story 31 — the board** (Sonnet, medium effort).

---

### 2026-08-05 — Story 31: the board

Priority 1/2/3 + Archived, live counts, create/edit/detail, and every action
from the design: complete, uncomplete, skip, archive, restore, delete, plus
Story 42's approve/reject. `nora_home/todo/views.py`, `forms.py`, `urls.py`,
`templates/todo/`, `static/nora_home/{css,js}/todo.*`. Mounted at `/todo/`
explicitly in `config/urls.py` — Todo is Level 2, so `house_app_urlpatterns()`
skips it (that helper only mounts Level 3 apps), the same as every other
platform app. **19 new tests (13 through the real views, 6 covering the
one-shot-task-state behaviour below), 685 green.**

Two decisions made while building, both now recorded in `todo.md` §6:

- **`awaiting_approval` gets its own strip above the board**, not a priority
  column. §4a says it "leaves the board's open columns" — true, but it still
  needs somewhere for the approver to see and act on it, so it renders above
  the columns rather than being sorted into one it has already, in the sense
  that matters, left.
- **A one-shot task's `Task.state` now follows its instance.** Completing,
  approving, or skipping the only instance a non-recurring task will ever have
  moves the task itself to `done`, which is what actually makes it leave the
  board (§4: "Done — finished, leaves the board, lives in history"). Nothing
  before this story needed a one-shot task to actually leave anywhere.
  `uncomplete()` reverses it. A recurring task's state never follows — it has
  no "last" occasion. `nora_home/todo/api.py` gained `skip()` and
  `uncomplete()` to hold this, alongside `complete()`/`approve()`/`reject()`.

**A real platform bug, not a Todo one — found by clicking the actual board in
a real browser instead of trusting the Django test client.** All 685 tests
stayed green through this the entire time. `NoraHome.post()` (`nh-app.js`)
builds a `FormData` for its POST body; for a zero-payload action — a tick, an
approve, a skip — that FormData has no fields, and this stack's ASGI request
handling rejects a *fully empty* multipart body outright with a bare, empty
400, before Django's URL routing, before any view, before any log line.
Chasing it meant going past `response.text()` (useless — the browser reports
"navigated away from" for a response that never actually caused a navigation)
down to intercepting the raw request with Playwright's `page.route()` and
replaying it by hand with `requests` to see the wire format. Once isolated,
checked whether it was Todo-specific — it was not: the **tracker's own
completion tick** hits the identical code path and was reproduced broken the
same way with a raw request, then confirmed fixed after. Fix is one line: a
`FormData` with zero keys now gets one harmless placeholder field, so the body
sent over the wire is never empty. Every existing zero-argument call through
`NoraHome.post()` was affected; the unit suite never noticed because Django's
test client does not build a real multipart body.

Next: **Story 32 — Reminders** (Sonnet, high effort). No longer blocked —
Story 30, its only real dependency, has been done since Story 30 itself
shipped; the dashboard's stale "Story 30 ▶" on 32/33/35 is fixed in this
commit too.

---

### 2026-08-05 — Story 32: reminders and escalation

`nora_home/todo/reminders.py` and `nora_home/todo/escalation.py`, two new
Celery beat entries (`todo.send-reminders`, `todo.run-escalations`, both every
5 minutes), and `api.acknowledge()` plus a "Seen it" button on the detail page.
**41 new tests (18 reminders, 23 escalation), 732 green.** Verified live in a
real browser, not just the unit suite: created a P1 task with a due date and
confirmed the default reminder actually exists in the database; hand-advanced
an instance past its due moment, ran the escalation sweep for real, saw "Escalated
to level 1" and a "Seen it" button render on the detail page, clicked it, and
watched the page flip to "Acknowledged by" — zero console errors.

**Reminders fan out to every assignee** (`api.doers()` — the same function the
effort-split calculation already uses); **escalation chases the owner alone**,
never the assignees, because a shared task still needs exactly one person the
ladder holds accountable — the fan-out and the accountability are deliberately
different mechanisms, not the same one reused twice. §8's "fire once, no
snooze" rule needed no new schema: `notify()`'s existing `dedupe_key` window
(30 days, keyed to the instance's own uuid) is what the build brief pointed at,
so a reminder firing twice is prevented by infrastructure that already existed,
not a new "sent" flag.

**Escalation is a genuine port of the tracker's engine**, not a rewrite — same
`EscalationPolicy` model, same ladder shape, same audience resolution
(owner/chain/adults/house), same "falls back to the house default policy when
none is set" resolution `register_trackable()` already uses. Two deliberate
departures, both because Todo already had a better answer than copying the
tracker's shape verbatim: no second `EscalationEvent` table (each rung fire is
a `ChangeEvent`, the same history table §4a's approval trail already uses), and
`acknowledge()` — new UI over `Instance.acknowledged_at/acknowledged_by`, which
have existed unused since Story 30 waiting for exactly this to arrive.

"Sound" is accepted as a `Reminder.channels` value and silently dropped before
reaching `notify()` — no audio channel exists in the platform's notification
backends yet (Story 38's job), and forwarding an unknown channel would have
been the cascading-failure shape CLAUDE.md rules out. Event reminders are
deliberately not evaluated yet either — a recurring event's next occurrence
needs the same calendar arithmetic Story 33 is going to build, and writing a
narrower version now just to unblock this story would be one more thing to
keep in sync once Calendar actually lands.

One test-fixture lesson, not a product bug: `tests/test_todo_escalation.py`'s
first draft mixed the top-level `member` fixture (which creates a member named
"kid") with the `household` fixture (which creates its own "kid") in the same
test — a straight `IntegrityError` on the username's uniqueness. Fixed by
giving `make_task` no `member` dependency of its own, taking `owner` as a
required argument instead, matching how the tracker's own `make_trackable`
fixture already avoids this.

Next: **Story 33 — Calendar** (Sonnet, medium effort).

---

### 2026-08-05 — Story 33: calendar

`nora_home/todo/calendar.py` (pure month-grid and yearly-event-recurrence
arithmetic, tested with no database), `views.calendar_view`,
`templates/todo/calendar.html`. **24 new tests, 756 green.** Verified live in
a real browser with actual demo data rather than just the unit suite: month
navigation (September 2026 rendered correctly after clicking "next" from
August), a completed task, a planned task, and a yearly-recurring event all
rendered on the correct days with distinct colour coding and the recurrence
marker on the event, zero console errors.

Three decisions settled by building rather than left to the design doc's
prose:

- **"Actual" means every non-`pending` outcome**, not only `done`. A `missed`
  or `skipped` instance is real history too, and hiding it would make a week
  that actually had a gap in it look empty instead — the same "a gap is
  honest, a zero says you failed" reasoning `tracker.api.completion_stats()`
  already uses. `awaiting_approval` counts as actual as well: the work
  happened, even though Reporting won't count it as a completion until
  approved.
- **Archived tasks are excluded, matching reminders and escalation** — "not
  now" means quiet everywhere. A `done` one-shot task (Story 31) is
  deliberately *not* excluded: its instance is the record of the day it
  actually happened, and hiding it because the task itself later finished
  would erase real history.
- **An out-of-range `?year=`/`?month=` falls back to today** rather than
  raising — a calendar that 500s on a hand-edited URL or a stale bookmark is
  worse than one that just shows the current month.

Scoped exactly like the board — `api.tasks_for(scope_members(request))` — so
a shared task appears on every assignee's calendar and the Everyone toggle
widens it for free, with no separate mechanism to keep in sync.

Next: **Story 34 — Search, Labels & Kiosk** (Sonnet, medium effort).

---

### 2026-08-05 — Story 34: search, labels, kiosk

`nora_home/todo/search.py` (`search_tasks()`, `FilterParams`), a new
`SavedFilter` model and migration, `views.search`/`save_filter`/
`delete_saved_filter`/`labels_view`, `templates/todo/{search,labels}.html`,
and Todo's `nora_kiosk_controls` declaration in `apps.py`. **37 new tests, 793
green.** Verified live in a real browser, including the kiosk: created a task
with "bird feeder" in its description, found it by that text on the Search
page; created a label from the new Labels-page form; saved a filter and saw
it come back as a chip; and — the part no unit test could check — opened the
actual kiosk page, tapped the Todo tile, and watched it switch to a screen
with exactly the three real buttons (Tasks, Due today, Calendar), each one
working.

**6.4 turned out to already be built.** The brief said to check whether the
kiosk's "everywhere + inside an app" system reached the whole house, and
extend it if not. It already did — built generically off the app registry
when the kiosk-drives-wall redesign shipped weeks ago — so Todo's kiosk
declaration needed zero platform-level code, only the declaration itself.
Confirmed by clicking through it on a running house rather than reading the
view function and assuming it still worked.

**Only 3 of the 5 documented kiosk controls are declared, on purpose.**
Reporting (Story 35) and System tasks (Story 36) don't have pages yet, and a
kiosk button linking to a 404 on a wall-mounted touchscreen is worse than one
that isn't there at all — the same reasoning `nora_has_page` already applies
to the Apps directory. `apps.py` has a comment marking where to add the other
two. "Due today" reuses the board at `/todo/?due=today` rather than becoming
a fourth page, so the priority-column and awaiting-approval logic stays in
one place.

**"Saved and returned to" is one function away from drifting**, so it was
built to make that impossible rather than merely unlikely: both the live
search page and a saved filter's "apply" link run through the exact same
`search_tasks(queryset, FilterParams)` call. A saved filter is stored as
`SavedFilter.params`, and applying it is a redirect to that same dict rendered
back as a querystring — there is no second function that could someday
interpret "priority=1" differently from the form that produced it.

**Full-text search over comments needed two join paths, not one** — a task's
own standing comments (`Task -> Comment`) and an instance's comments
(`Task -> Instance -> Comment`) are different relations to the same `Comment`
model, both real per §4's "comments attach at both levels." Combined as one
queryset filter (`Q(comments__body__icontains=...) | Q(instances__comments__
body__icontains=...)`) rather than two separate queries fed back in — the
first draft tried the two-query version and it was both slower to reason
about and required a manual `.distinct()` that a plain queryset filter needed
anyway.

Next: **Story 35 — Analytics & Reporting** (Opus, high effort).

---

## 2026-08-05 — Story 35, Analytics & Reporting, finished from an interruption

Picked up mid-story. `analytics.py`, `widgets.py`, `tone.py` and the reporting
view had landed in commit `0e7a344`; the templates they render, the script that
draws the charts, and every test of the arithmetic had not. **Both
`/todo/reporting/` and `/todo/settings/` were 500s** on `TemplateDoesNotExist`.
Added `_chart_card.html`, `settings.html`, `todo-reporting.js`, the Reporting and
settings CSS, and `tests/test_todo_analytics.py`. 66 new tests, **857 green on
the Pi**. Full writeup in
[`subsystems/todo.md`](subsystems/todo.md) §10 "As built".

**Three real bugs, and the one the story was flagged for was real.**
`priority_distribution()` counted one task per priority — `Task.Meta.ordering`
is `["priority", "-created_at"]` and Django appends ordering fields to the
`GROUP BY` of a `values().annotate()`, so it grouped per task and every count
came back as `1`. A perfectly plausible table full of wrong numbers. Caught only
because the test used three tasks in one priority. Also `.pane` (a class that
does not exist here — the glass class is `.card`) on five cards, and
`today.replace(year=year - 1)`, which raises on 29 February, in both the heatmap
chart and the heatmap widget.

**Looking at the wall found what reading the template could not.** The first
version rendered an empty house as twelve near-full-size cards each saying
"Nothing finished yet." — breaking two of §10's own six rules on the page
written to avoid them. Fixed, and two tests now hold it in both directions.
Verified on the real hardware end to end: tapped the kiosk's Todo tile, then the
new Reporting button, and watched the wall follow.

### The `.env` trap — read this before touching the Pi

**`.env` is tracked in git** (committed in `a173dcf`, which also removed the
`.env` line from `.gitignore`). The committed copy carries `.env.example`'s
*laptop* defaults. So **every `git pull` on the Pi replaces the house's real
configuration**: `config.settings.pi` → `dev`, MySQL → SQLite, `America/New_York`
→ `America/Los_Angeles`, `DEBUG=0` → `1`, ports 443/80 → 8443/8080, and the real
Slack and MCP tokens → empty. It happened twice during this session.

The failure is quiet and looks like data loss. A pull swaps the file; nothing
changes until a container is recreated, and then *that* container comes up on a
fresh empty SQLite database in its own writable layer — there is no volume for
`db.sqlite3`. `web` served an empty house while `worker` and `beat`, never
recreated, kept running on MySQL with all the data. CLAUDE.md's own warning is
the thing that saves you here: **a container keeps the environment it started
with**, which is also what makes the still-running container the best available
record of the correct configuration.

Recovering, if the configuration is ever wrong again: rebuild `.env` from a
container that has not been recreated —
`docker inspect nora-home-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}'`
— then `./nora recreate`. Nothing is lost; MySQL still holds everything.

**Fixed the same day.** `.env` and a leftover `.env.check_tmp` (a scratch copy
from an earlier session, carrying the same values) are untracked, and
`.gitignore` now reads `.env` / `.env.*` with `!.env.example` — the class, not
the one file, so the next `.env.bak.*` or `.env.something` a session leaves
behind cannot repeat this. Both files stay on disk on every machine that has
them; only git stops following them. The repo is private and the briefly
committed values are staying as they are, decided explicitly.

The `db.sqlite3`-in-the-container-layer half is **not** fixed and was never the
cause here: it only matters when the house is running on `dev` settings, which
it should never be. Worth knowing if anyone ever points the Pi at SQLite
deliberately — there is no volume, so that house has no persistence.

### `db.sqlite3` was briefly tracked too, from a restore — now re-ignored

Restoring `db.sqlite3` from an older machine (a laptop dev copy — three house
members, ten Todo tasks, all test data, nothing real) re-added it to the repo
and dropped its two `.gitignore` lines. Checked before doing anything: `pragma
integrity_check` clean, all five Todo migrations present and matching what's on
disk, and Django could query it — genuinely good data, not corruption. Copying
it into the Pi's container and running `analytics.overview()` against it
independently confirmed the Story 35 GROUP BY fix: priority mix came back
14.3/71.4/14.3% across three tasks, which is exactly what the bug would have
broken.

Re-ignored the same day, same reasoning as `.env`: a dev database is
machine-local state, not source. Tracking it meant a permanently dirty working
tree, a fresh ~1.1MB blob in every commit that touched it (SQLite does not
delta-compress), and binary conflicts between machines with no real merge. The
file stays on disk and keeps working; git stopped following it.

---

## 2026-08-06 — Story 36, System Tasks & Telemetry Bridge

`nora_home/todo/system_tasks.py` bridges telemetry and integrations into a
`source=system` board at `/todo/system/`, one-directional by construction: it
listens to `threshold_crossed` (already fired by
`telemetry.api._raise_threshold`) and a new `integration_failing` signal (fired
once per continuous-failure episode from `integrations.tasks._record_failure`,
alongside the `notify_house` call already there), and creates a `Task` from
what it hears. Nothing reads a task back into either subsystem. Full writeup:
[`subsystems/todo.md`](subsystems/todo.md) §8 "As built".

The dedupe rule is the load-bearing part: `_raise_threshold` fires on every
off-threshold reading, so without it a stuck sensor would put a fresh task on
the board every few minutes. `Task.origin_ref` (new field, migration 0006) plus
a check for an already-open task with the same ref is what keeps a continuous
problem as one task — completing it starts a fresh one on the next occurrence,
correctly treating that as a new instance of the problem rather than a
continuation.

The board is a refactor, not a new page: `views.board()` and the new
`views.system_board()` share one `_board_context()` and one template, switched
on `is_system` — the shape §8 asks for ("the same board, same shape"). 22 new
tests, **881 green on the Pi**. Verified against SQLite through the real
signals (not a direct call to `create_system_task()`, so a dropped `.send()`
would have been caught), then against the Pi's real MySQL with the migration
applied and rolled back inside a transaction, then on the physical hardware —
tapped the kiosk through Todo → System and watched a demo task appear on the
wall, its default reminder firing a real alert, before being cleaned up. All
five documented kiosk buttons now exist.

**Story 40 (Tracker Removal & House Log) is unblocked** — its only two
dependencies were Stories 35 and 36.

### A real, pre-existing test flake found while verifying the deploy

Rebuilding the Pi's image `--no-cache` from a clean git checkout (rather than
the hot-patched container used through most of this story's development) and
re-running the suite turned up **7 failures, all in
`tests/test_todo_reminders.py`**, none in anything Story 36 touched. Confirmed
by direct reproduction, not assumed: a task due "today" with no explicit
`due_time` falls back to the owner's default hour (09:00), and the suite ran at
00:08 local — nine hours before that reminder is actually due. Constructing the
same scenario with an explicit `due_time` set to the current moment sent a
reminder immediately (`{'sent': 1}`); the identical scenario relying on the
9am default correctly returned `{'sent': 0}` with `due_at` nine hours out. The
reminder logic is right; the tests assume the suite always runs after 9am
local, and `TODAY = timezone.localdate()` at module scope gives them no way to
control for it. No time-freezing library (`freezegun`/`time-machine`) is in
`requirements/`, so tests can't yet pin "now" the way this needs. **Not fixed
here** — deliberately out of scope for Story 36, since it touches unrelated
test infrastructure rather than anything this story built. Flagged separately.

With those excluded, **874 passed** on the clean image, all other subsystems
green including `test_todo_system_tasks.py` at 22/22 in isolation.

### 2026-08-06 — ahead of Story 37: Slack IDs recorded, command shape decided

Two real house members set up ahead of the Slack build. `priya` did not exist
as a `HouseMember` yet — added via the documented `add_member` command
(`python manage.py add_member priya --display-name Priya --role admin`), same
path any real member gets added, not a one-off. Both `nitin` and `priya` now
carry a real `slack_user_id` (`U098WCK1JGM`, `U098YALDXRQ`), set directly since
the `slack_members` matching command needs the workspace connection Story 37
builds.

**Command shape changed from three slash commands to one.** The design doc
originally specified `/todo-ack`, `/todo-approve`, `/todo-new` as three
separately registered Slack commands. Asked directly which was better, decided
on a single `/todo` with subcommands instead — one command to register in the
Slack app config, one Socket Mode handler routing all of it, a future action
is a new case rather than new Slack-side setup. todo.md §12 and the build
brief updated before any Story 37 code exists, so the design doc and the code
never had a chance to disagree.

---

## 2026-08-06 — Story 37, Slack Socket Mode, verified against the real workspace

The house gains an inbound half. `nora_home/notifications/slack_socket.py`
holds one outbound websocket; `slack_commands.py` beside it is a registry that
resolves a Slack user id to a `HouseMember` and knows nothing else;
`nora_home/todo/slack_commands.py` is what `/todo` actually means. Todo
registers into the registry from its own `ready()`, so the base platform never
imports the app by name — the same seam `IntegrationsConfig` uses. Buttons
travel as `slack_actions` in the notification context, so the Level 1 channel
renders controls without learning what a task is. **45 new tests, 924 green.**
Design notes in [`subsystems/todo.md`](subsystems/todo.md) §12 "As built".

**Two real bugs, both found by running it rather than reading it.**

The first came from a *failing test*, and it was a genuine design fault, not a
bad assertion. `api.skip` refuses once `due_at` has passed — §5 is explicit
that the occasion is a miss by then, and calling it a skip would launder a miss
out of the pattern data Reporting is built on. But the default reminder fires
*exactly at* `due_at`. So the Skip button would have shipped present and
permanently broken on almost every reminder the house sends. It is now offered
only while declining is still a decision, which is the rule §10 already applies
to empty charts: do not draw a control that cannot act.

The second came from **tapping a real button in Slack**. Slack sends a
`block_actions` interaction for *URL* buttons too — so "Open in Nora Home"
dispatched into the registry, found no handler, and replied "that button no
longer does anything" while cheerfully opening the page it pointed at. Link
buttons are now recognised by their `url` and answered with silence. The log
line that gave it away read `No handler registered for Slack action '68IXC'`,
because Slack invents a random `action_id` when one is absent; that button now
carries an explicit one.

**A deployment trap worth remembering.** The first live test message arrived
with no buttons at all. The rendering happens in the **worker**, not the web
container, and `docker compose up -d web` had left the worker on the previous
image. Nothing errored — old `_blocks()` simply ignored the `slack_actions` it
had never heard of. Any change to notification *rendering* needs the worker
recreated, not just web.

Also confirmed against Slack's live docs rather than this file's own claim
(§12 asked for exactly that): **10 concurrent Socket Mode connections per app**,
payloads arriving on any of them. This house opens one, from one container —
which is also why the socket must never run inside the worker.

### The wall had been blanking every ten minutes, and my own activity hid it

Noticed only because the user looked up and said both screens were off — at
14:30 on a Thursday, which the house's own overnight schedule (01:00–08:00)
cannot explain. `xset -q` gave it away: `Standby: 600  Suspend: 600  Off: 600`,
`Monitor is Off`.

**`provision-pi.sh` disabled the X screensaver but not DPMS.** They keep
*separate* idle timers, and `xset s off; xset s noblank` only silences the
first. DPMS's own 600-second defaults went on blanking both screens after ten
minutes without input — which, on a wall-mounted display nobody touches, means
every ten minutes forever. The provisioning comment was reasoning correctly
about the *other* half of the problem (DPMS must stay enabled, or the overnight
schedule's `dpms force off` becomes a no-op) and stopped one step short.

**It stayed invisible because every screenshot I took today followed an
`xdotool` click**, and any input resets the idle timer. The screens looked
perfect for exactly as long as someone was poking at them — which is also why
this survived the earlier hardware verification sessions.

Fixed with `xset dpms 0 0 0` alongside the existing calls: zero means "never
fire", so the idle timers stop while DPMS stays *enabled* and forced power-off
still works. Both halves verified on the Pi rather than assumed — no blanking,
and `dpms force off` / `force on` still drive the panels. Applied to the live
autostart file and to `provision-pi.sh`, so a reprovisioned or fresh Pi gets it
too.

### Story 38 was not blocked either

Asked what was blocking it and checked instead of repeating the label. Its only
dependency (Story 32, Reminders) is complete; both HDMI audio devices exist
(`vc4hdmi0` = the wall, `vc4hdmi1` = the kiosk); and `aplay`, `ffplay` and
`speaker-test` are already installed, so no new packages are needed.

**The 24"'s speakers are confirmed working** — a 440Hz tone was played through
`plughw:0,0` and the user heard it clearly in the room. That is the one fact
that could not be established from software alone (an HDMI audio *device*
existing says nothing about whether the panel has speakers), and it is what
makes Story 38 buildable exactly as written rather than needing an alternative
output path.

The "blocked" readiness was stale in the same way Story 37's had been — with
**nothing in Phase 7 blocked any more**. One trap recorded for whoever builds
it: playback must go through **`plughw:0,0`**, not `hw:0,0`. The raw device
rejects the parameters outright — "Setting of hwparams failed: Invalid
argument" — while `plughw` lets ALSA convert and plays fine.

---

## 2026-08-06 — Story 38, Alarms & House Audio, heard on real hardware

The house gains a voice. `nora_home/notifications/tts.py` is the seam —
`UnconfiguredTTS.synthesize()` raises `TTSError` rather than faking a voice,
so a speech alarm degrades to silence instead of breaking anything around it.
`nora_home/todo/alarms.py` resolves a task's `alarm_kind`/`alarm_ref` to bytes
(chime from a bundled asset synthesised with Python's own `wave` module —
`static/nora_home/audio/chime.wav`, not fetched from anywhere; file from
object storage; speech through the TTS seam) and never raises — every failure
degrades to "no sound." `nora_home/notifications/channels/sound.py` cannot
play anything itself (the speakers are on the host, Django is in Docker) — it
writes resolved audio to a bind-mounted cache; a host script on a systemd
timer, generated by `provision-pi.sh` the same way the wall power schedule
is, plays the newest file. **29 new tests, 955 green.** Design notes in
[`subsystems/todo.md`](subsystems/todo.md), "Alarms" § "As built".

**A real bug caught before it shipped, not after.** The first draft passed
resolved audio bytes through `Notification.context` so `SoundChannel` could
play them — `context` is a `JSONField`, and raw bytes do not survive a JSON
round trip. Fixed by having the channel re-resolve the alarm itself from a
task id at delivery time, which is also simply more correct: the task's alarm
could have changed between the reminder firing and delivery actually running.

**Gated on the task's own `alarm_kind`, not on `Reminder.channels`.** The
design doc's own framing suggested routing sound through a reminder's channel
list the way Slack/inapp/display already are. Checked before building it: no
template anywhere lets a person put `"sound"` into that list, so gating on it
would have made the alarm form field — already built, Story 42 — do nothing.

**The backlog rule (§10.4) has two independent lines of defence, not one
duplicated.** `send_due_reminders()` collects every alarm-eligible task due
in one sweep and, if more than one, plays sound for only the most recent
while the rest become a single text summary. Separately, the host script only
ever plays the single newest file since it last checked — which is what
protects the house even if the Pi being off meant several sweeps' worth of
files piled up in the cache before the timer ran again.

**Story 38 was not actually blocked**, the same way Story 37's flag turned out
to be stale. Checked rather than repeated: its only dependency was complete,
both HDMI audio devices exist on the Pi, and `aplay`/`ffplay`/`speaker-test`
were already installed. The one fact that genuinely needed checking —
**whether the 24" monitor has working speakers at all** — was settled by
playing a real 440Hz tone through `plughw:0,0` and having the user confirm it
was heard clearly in the room. `hw:0,0` rejects `speaker-test`'s own
parameters outright ("Setting of hwparams failed: Invalid argument");
`plughw:0,0` is what every playback path in this story uses.

Phase 7 is now **12 of 15 (80%)**. Story 39 (Wall Type Scale) is the only
small piece left; Story 40 (Tracker Removal) and Story 24 (house maintenance,
the first real app) are the two substantial open choices.

---

## 2026-08-06 — Story 39, Wall Type Scale

One line of CSS is the type scale itself: `html[data-surface="wall"] {
font-size: 160%; }`. Every size in `nora-home.css` is already `rem`, and rem
is always relative to the root, so one multiplier scales the whole system
together — "same templates, same CSS, one variable" turned out to be
literally true, not just the goal.

**What made that one line insufficient by itself, and the actual work of this
story:** the wall's shell page matches `data-surface="wall"` correctly, but
the real app content it iframes (`/home/`, `/todo/`, wherever the kiosk points
it) is requested at its own ordinary URL, indistinguishable from the same
page opened directly on someone's laptop. `SurfaceMiddleware` (`nora_home/ui/middleware.py`) now tells the two apart statelessly, using
`Sec-Fetch-Dest: iframe` plus a same-origin `Referer` naming the wall's own
page — not a cookie, since a cookie set once would leave a stray laptop
preview stuck wall-sized until someone thought to clear it.

`DashboardLayout.Surface.WALL`, dead code since the skeleton, is now
load-bearing: `dashboard/views.py` gained `_layout_for()`, which every
layout-touching view calls, so the wall always shows the layout curated for
it rather than whoever is signed into its browser. The "editor reachable from
a phone or laptop" §11.2 asks for turned out to be a third option on the
existing topbar switcher ("Wall", beside "Everyone"), not a new page — same
picker, same drag-and-drop, `wall_safe` now enforced in `save_layout()`
itself rather than only in what the picker offers.

Deliberately not built: §11.3's configurable wall boot destination — separate
work, no dependency on anything here.

38 new tests, 971 green. Phase 7 is now **13 of 15 (87%)** — Story 40
(Tracker Removal) and Story 24 (house maintenance, the first real app) are
the two substantial pieces left.

**A second bug surfaced by actually looking at the deployed wall**, not by
reading the diff: the "House health" stat tile rendered with its value
clipped, the top of "OK" sheared off by the tile's own `overflow: hidden`.
Gridstack's `cellHeight: 80` is a bare number — a fixed pixel height that
never saw the wall's 160% root font-size — so tiles stayed 80px per grid row
while the stat value inside them grew past that fixed box. Fixed with
Gridstack's own `cellHeightUnit: "rem"` option (`cellHeight: 5` resolves to
exactly the same 80px at the normal root, nothing else changes) plus the
matching fix in the CSS-only fallback used when the vendored script fails to
load. Purely a browser layout fact, not something the Python suite could
have caught — confirmed by rebuilding, redeploying, and re-screenshotting
the real wall a second time.

---

## 2026-08-06 — Story 40: the tracker deleted, and the House log built

`nora_home/tracker/` is gone — models, API, widgets, cards, views, urls,
templates, and its three Celery beat jobs, whose successors in Todo had been
running alongside them since Story 31. `prune_beat_schedule` (already run by the
entrypoint before beat starts) dropped the three orphaned `PeriodicTask` rows on
the Pi by itself, which is what stops beat dispatching to import paths that no
longer exist. Confirmed on the Pi: the schedule now lists ten jobs, none of them
`tracker.*`.

**The migration was the whole risk, and not where the story expected it.**
`Task.escalation_policy` was a string reference to `tracker.EscalationPolicy`,
and *both* of Todo's earlier migrations carried a dependency on the tracker's.
A migration naming a node no installed app can supply does not degrade to a
warning: Django refuses to build the graph at all, and every management command
— `migrate`, `check`, `shell` — dies with `NodeNotFoundError`. So the
dependency had to go, which meant editing `0001_initial`, against CLAUDE.md §6's
"never edit an applied migration."

That rule's purpose is preserved rather than waived: `EscalationPolicy`'s
`CreateModel` block was copied verbatim out of the deleted
`tracker/0001_initial`, so replaying Todo's history from empty produces exactly
the table the unedited version did. `0007` is what converges databases where the
*original* already ran, and it does the whole job with one `RENAME TABLE`.
Renaming carries the rows, their primary keys and their indexes across, and — on
both MySQL and SQLite — rewrites the foreign keys in *referencing* tables to
follow the new name. So `todo_task`'s constraint ended up pointing at
`todo_escalationpolicy` without anyone dropping and recreating it, which is the
step that would otherwise have needed vendor-specific SQL and a lookup of
MySQL's auto-generated constraint name.

**Rehearsed before the live database was touched.** The tracker's schema (no
data) plus its `django_migrations` rows were dumped out of the running house
into a throwaway `nora_rehearsal` database, and the new migrations run against
that first: 3 policies carried with primary keys 1/2/3 and `is_default` intact,
0 tracker tables left, `todo_task`'s FK repointed by MySQL itself, the orphaned
`django_migrations` row cleared, `migrate --check` clean, and a real
write-then-read through the FK. Only then was it run for real, after a full
`./nora backup`. The live result matched the rehearsal exactly.

**The House log** (`/home/log/`, under House in the sidebar) merges five
subsystems onto one filterable timeline, and is built on one rule: **record what
changed, not what ran.** That rule came from measuring the real house before
writing any of it — over seven days it held 563 health snapshots of which **0**
were unhealthy, 275 integration runs of which **1** failed, 4 notifications, 4
deliveries of which 2 failed, and **0 audit rows**. A page listing all 563
health snapshots would have been 563 rows saying "everything is fine" with the
one row that mattered unfindable. So: health shows transitions only (and looks
one snapshot *before* the window, so a change at its very edge still reads as a
change rather than as the house's first-ever state); integrations show a failure
and the recovery that ends it; deliveries show only what did not arrive, because
a delivery that worked is the absence of an event; notifications and audit rows
show in full, audit because `record()` is curated at the call site. On the real
house that collapses 275 integration runs into the two entries that say the
weather integration broke at 17:30 on 4 August and recovered at 18:05.

**Which is why §12.3 shipped with it.** Audit had four call sites and three were
being deleted, so the page would have launched empty. `record()` is now called
for signing in as someone (there is no password in this house, so tapping a name
*is* the whole authentication story, and this row is the only durable record of
it), scope changes, setting changes — carrying the new values, because "why did
the wall go dark at six" is only answerable if the log says what the hours became
— app install and uninstall (at warning severity when data was purged, since
that is not the same event as unmounting), backups succeeding and failing, and an
integration entering a failing episode. The last is written on `== threshold`
rather than `>=`, so an integration down for a day writes one row rather than 288.

Todo also picked up the two MCP tools the tracker published — `open_items` and
`member_reliability`, same tool names, now answering from `Instance` history.
`open_items` matches on owner *or* assignee, since an agent asked "what does
Priya need to do" that only matched `owner` would silently omit every shared
task. `house_overview` keeps its counts but degrades to `None` when Todo is
absent rather than raising inside the first tool an agent calls.

Verified: 884 tests green (down from 971 — three tracker test files went with
the app; 28 new ones cover the log), the migration rehearsed and then applied
live, all ten services healthy afterwards, every platform page still 200, and
the page itself seen on the physical wall with both charts rendering real data
and the nav entry in place.

**Two things left honest rather than papered over.** The wall cannot scroll — it
has no input devices by design — so only the top of the log was visible there;
the timeline rows themselves were confirmed from the rendered markup and the
unit tests, not with eyes on a screen. And ECharts draws its legend and axis
labels at fixed pixel sizes that do not follow the wall's 160% root, so the two
charts are legible on a laptop and small at three metres. That is a
pre-existing property of every chart in the house, not something this story
introduced, and the House log is a page you read from a phone or laptop rather
than a wall page.

**One gap this exposed and deliberately did not close.** The tracker published
`register_trackable()` — the call `DEVELOPMENT.md` tells house-app authors to
make so the platform handles their due dates, nudges and escalation. Todo has no
equivalent, so that recipe currently has no working call behind it. What it
should look like on Todo's model is a design question, not a deletion one, so it
belongs to Story 24's requirements gate; the docs now say so plainly instead of
pointing at a function that no longer exists.


---

## 2026-08-06 (later) — the wall, after the tracker went

The user looked at the 24" and said it was "all zoomed in, text huge and
overflowing", with the laptop and the 10.1" kiosk both fine. Two unrelated
faults, one of them a regression from Story 40 earlier the same day.

**Every stored layout still named the tracker's widgets.** `DashboardLayout`
skips a key it cannot resolve rather than raising — right for an app somebody
uninstalled, and wrong here. Deleting the tracker silently stripped three or
four tiles from *every* home screen in the house, the always-on wall included,
which was left showing one card. The Story 40 commit even documented this
behaviour approvingly ("tiles quietly disappear rather than getting an error
page"), which is the mistake: graceful degradation is not the goal when the
widget has an exact successor sitting right there. `dashboard/0002` retargets
them — `TodayWidget → todo.DueNextWidget`, `OverdueWidget → todo.OpenLoadWidget`,
`ReliabilityWidget → todo.CompletionHeatmapWidget`, `StreakWidget →
todo.StreakWidget` — matching *kind* for kind, because a layout is a grid of
boxes with stored widths and heights and a stat dropped into a box drawn for a
list is a different bug. It drops duplicates rather than rendering the same
widget twice. Confirmed on the Pi: all four layouts (both people's, the shared
one, and the wall's) now carry only keys that resolve.

**The type scale never actually reached the layout.** Story 39's write-up said
one CSS rule scales everything "because every size in `nora-home.css` is already
rem". It was not: `--nav-width: 244px` and `--tap: 44px` were pixels, so the
sidebar held laptop width while its labels grew 1.6× — "Measurements" was cut
off mid-word. **That is the same trap Story 39 itself found and fixed hours
earlier** in Gridstack's `cellHeight: 80`, in the same stylesheet, written up in
its own as-built notes. Fixing the instance and not the class is how it came
back. `--nav-width`, `--tap`, the card grid's `minmax(280px, 1fr)` and the
ornaments that sit beside text are all `rem` now.

With the clipping gone, 160% was still too much on its own terms: it leaves a
1920px screen only ~1200px of usable CSS width, so the page is laid out as a
small laptop and then magnified — one tile per row, the greeting spanning
everything.

**Then the better question: "should that not scale automatically by display
size?"** It reshaped the fix. **A CSS pixel is already a *reference pixel*** —
the visual angle of one pixel on a 96dpi screen at arm's length — and the
browser normalises for physical size through `devicePixelRatio`, which is why a
460ppi phone reports ~390 CSS px rather than 1170. Websites get physical-size
normalisation for free; they get it for the one distance the web assumes. The
input nothing can measure is **viewing distance**, and the 24" and a laptop both
report 1920×1080. That is what `data-surface="wall"` actually carries: not
pixels, but ~3 metres.

**The platforms with this problem solve it one layer down, so we do now too.**
TV and signage never magnify a desktop layout — a 4K TV browser reports 1280 CSS
px and lets the compositor upscale. Chromium exposes the same lever, and the
wall's launch script now uses `--force-device-scale-factor`. The kiosk stays at
1: a touchscreen at arm's length is the default case.

**Every CSS version was wrong for the same reason, and the `vw` one included.**
Scaling the root font-size grows each `rem` while borders, shadows and corner
radii stay 1-device-pixel hairlines. The proportions come apart and it reads as
*zoomed* even when the text size is right — which is exactly what was reported,
twice. 1.5 was tried first and overshot: it reports a 1280px viewport, narrow
enough that the topbar wrapped the profile icon under the greeting, and it landed
physically *larger* than the 135% it replaced (60 vs 54 device px on an h1) when
the whole complaint was that the wall looked zoomed. **1.25** reports 1536 — an
ordinary laptop width — so the wall gets a real laptop layout rendered slightly
larger rather than a compressed one. Worth knowing before reaching higher:
nothing in this range makes body text readable at three metres; that needs
roughly 90px type. The wall is a glance surface.

**Which exposed an operational hole, and closed it.** `~/.nora/start-*.sh` are
*generated* by `provision-pi.sh`, so a new Chromium flag does not reach the
running screens through a deploy, a page reload, or a reboot. That had already
caught this project once — when HTTPS moved the app off `:8000` and the wall was
still opening the old URL — and was fixed by hand both times. **`./nora screens
relaunch`** now regenerates both scripts and restarts both browsers. It re-runs
only `launch_script()` out of the provisioner (the rest is already satisfied on a
running house, and several steps need sudo a non-interactive session cannot
answer), and reads *both* the function and its call lines from that file so it
cannot drift — a throwaway version of this used while fixing the wall hardcoded
the scale factor and silently regenerated the old value after it had changed.

**And the suite turned out to fail after midnight.** Running it at 00:07 gave 11
failures across reminders and alarms; the identical code passed when only the
timezone was shifted so "now" was 10:09. Two independent clock dependencies, both
of them the tests being vague rather than the code being wrong: a task with a due
date and no due time falls due at the 09:00 default hour, so nothing due "today"
has come due yet before breakfast; and sound follows the house-wide quiet-hours
window, which defaults to 22:00–07:00, so `queue_alarm()` rightly refuses to make
a noise at midnight. Both fixtures now state their assumption — `due_time` pinned
to midnight, and an autouse fixture setting `start == end`, which `is_quiet_now()`
reads as never quiet. **Verified by running the full suite at 00:14, the hour
that had been failing: 891 green.** This had been noticed once before and filed;
it is now fixed, because CLAUDE.md's claim that the suite "gives the same answer
on a laptop and on the Pi" has to mean at any hour too.

`tests/test_ui.py` now reads the stylesheet and the launch script as text: the
wall's scale factor must be in `provision-pi.sh` and in range, the kiosk must not
be scaled, the scale must *not* have come back in CSS, and
`--nav-width`/`--tap`/the card-grid minimum must be `rem`. No unit
test can see a browser layout — both instances of this bug were found by
looking at the physical screen — but the class is catchable even when the
instance is not, and that is what was missing. `tests/test_dashboard.py` also
now asserts that no stored layout and nothing in `STARTER_LAYOUT` names a
widget that does not resolve.

891 tests green on the Pi, all ten services healthy, and the wall re-screenshotted
showing the full nav uncut and four tiles in a proper grid.

**And one more thing the user found by simply reading the screen: "there is
nitin, priya, everybody, what's that other user named wall?"** The profile
switcher listed *Everyone* and *Wall* as plain buttons in the same flat list as
the household, under a heading that said "signed in as nitin" — so a view scope
read as a fourth family member. They are not people: they change *what you are
looking at*, not *who you are*. Both now sit under their own "Show me" heading,
separated by a rule, each with a line saying what it does; "Wall" is now
`The 24" wall — what the big screen shows, rearrange its tiles from here`,
which also finally explains §11.2's remote layout editor at the point of use
rather than only in the design doc.

---

## 2026-08-07 — screen size becomes a setting, and two commands that lied

"just allow me to set the zoom level for the 24inch and the 10inch display in
the screen section in settings... for displays like laptop or phone, it already
looks fine, so why mess with it." Right on both counts, and it settled a
question three previous answers had got wrong.

**Settings → Screens now has a zoom per fixed screen** (`nora_home/ui/zoom.py`,
stored in `HouseSetting`, applied as CSS `zoom` on `<html>`). Phones and laptops
are untouched — `nh_zoom` is `None` for them and no attribute is emitted at all.

**Why CSS `zoom` and not the device scale factor**, having argued the opposite
hours earlier: `--force-device-scale-factor` is the more native mechanism and
what TV and signage platforms use, but a launch flag can only be changed by
regenerating the launch script and restarting Chromium — an SSH session. A number
a family member is expected to tune has to live where they can reach it. Both
screens now launch at scale 1 so the two cannot multiply.

**It was measured before it was chosen**, on the Pi's own Chromium, because
"zoom scales everything" needed to be a fact rather than a hope:

    a 100px box with 10px borders   plain 120px  ->  zoom 1.25  150px
    html { zoom: 1.25 } on 1920     documentElement.clientWidth   1536

Both match `--force-device-scale-factor=1.25` exactly. That is the property
scaling the root font-size never had, and the whole reason it read as "zoomed"
at 160% and again at 135%: `zoom` grows borders, shadows and radii with the
text instead of leaving them as 1-device-pixel hairlines. One difference worth
writing down rather than rediscovering: media queries still evaluate against the
*unzoomed* viewport, which is immaterial on the wall but would matter on the
1024px kiosk — hence its lower ceiling.

**And then the feature appeared not to work, which found two commands that were
lying.**

Storing 1.05, then 1.8, then reloading, changed nothing on the wall. The tests
passed, the setting stored correctly, and the served HTML carried the right
`zoom`. The evidence that settled it was nginx's access log: **the wall requested
its pages once, when it launched, and never again** — across several runs of
`./nora screens` that each reported "ok reloaded wall".

`./nora screens` sent `ctrl+shift+R` with xdotool. Chromium in `--kiosk` ignores
the reload shortcut, so it had been reporting success and doing nothing —
including after every deploy that changed a template, for as long as it has
existed. It now broadcasts a `refresh` on the displays bus, which is the same
websocket the kiosk already uses to drive the wall and which both screens handle
by calling `window.location.reload()` themselves. No window focus, no X server,
no guessing at window titles, and it fails loudly if the bus is unreachable.

The other was mine, and smaller: the throwaway helper used to regenerate the
launch scripts hardcoded the scale factor, so after the value changed it
silently rewrote the old one. **`./nora screens relaunch`** now exists as a
supported command, and reads both `launch_script()` *and* its call lines out of
`provision-pi.sh` so it cannot drift from what provisioning would actually do.
That gap — the launch scripts being generated, so a new flag never reaches a
running screen through a deploy or even a reboot — had already caught this
project once, when HTTPS moved the app off `:8000`.

Verified end to end on the hardware: zoom set through the real form, `./nora
screens`, and the wall visibly smaller in the screenshot; then set to 1.15 and
left there. 906 tests green.

---

## 2026-08-07 — Story 41: Tests, Docs & Deploy — Phase 7 complete

87 new browser tests, `tests/qa/test_todo_qa.py` — the layer `./nora test`
cannot reach: rendered pages, `todo.js` actually running, real clicks. Board,
calendar, reporting, search, labels, settings, create and system pages all
smoke-tested the same way `test_smoke.py` covers the platform; a task created,
completed and archived **through the browser and reloaded**, the same pattern
`test_journeys.py`'s widget test uses and for the same reason — a POST that
403s and gets ignored by `fetch()` looks identical to success until the page is
asked again; no sideways scroll at the five real screen sizes; card and figure
contrast measured from pixels across every theme × daypart.

**It found two real accessibility bugs the whole session's worth of unit tests
never could, because neither is expressible as a Python assertion.**

`.todo-card` had no glass pane at all — unlike every other surface in the
design system, a task card sat directly on the raw living background. Dark
theme's near-white text measured as low as **2.04:1** against a bright midday
sky. A second, smaller bug compounded it: the title's `<a>` inherited the
global `a { color: var(--accent) }` rule with nothing in `todo.css` to stop it
— the exact bug `.brand` had (CLAUDE.md, 2026-08-04), never fixed here. Giving
`.todo-card` the same `rgba(var(--pane-rgb), 0.3)` + `backdrop-filter` pane
every other card in the house already has, and setting the link's colour to
`var(--text)` explicitly, cleared every theme × daypart combination at **8:1 or
better** — measured, not eyeballed, the same way the light-theme dusk bug was
fixed in an earlier session. Reporting's `.todo-figure` stat strip had the
identical gap (no pane, correct text colour, so **borderline** rather than
badly broken — 4.11:1 against the 4.5:1 line) and got the same fix.

**Then a real scare that turned out to be a false alarm, and the process for
telling the two apart is worth keeping.** A full run of the 87 tests
consistently seemed to leave three tasks behind — titled uniquely, one per
creation test, surviving every re-run despite each test's own `finally:`
cleanup. Chased for over an hour: verified the delete endpoint directly
(`page.request.post`, a real 200, confirmed gone from the board); found and
fixed a genuine narrower bug along the way (a *done* one-shot task "leaves the
board entirely" per `api.py`'s own contract, so cleanup that only checked the
open board and the archived column had a blind spot — fixed by capturing the
task's href at creation instead of re-finding it afterward); added a
session-level teardown sweep as a second guarantee regardless. And still, after
all of that, a fresh full run appeared to leave three behind.

**The bug was in the verification, not the product or the tests.**
`Task.delete()` is `SoftDeleteModel`'s — it sets `deleted_at`, it does not
remove the row — and every "is there still litter?" check used
`Task.objects.filter(...)` without `.alive()`. `Task.objects.alive().filter(
title__icontains="QA")` was **0** the entire time; the per-test cleanup worked
on every single run. The lesson worth keeping: when a verification and the
thing it is verifying disagree for longer than it takes to check the
verification's own assumptions, check the assumptions first — `.alive()` is
exactly the kind of default that is invisible until you go looking for it,
which is the same shape of trap `docs/Main_App/subsystems/todo.md` §13 already
warns about for cached counters.

**Deployed and confirmed on the Pi over SSH**, since Playwright needs a real
Chromium and this Mac has neither Python nor a browser toolchain installed —
`~/.nora-qa-venv` (one-time `pip install -r requirements/dev.txt && python -m
playwright install chromium`, ARM64 build, ~111MB) runs `./nora qa`'s
equivalent directly on the Pi against `https://localhost`, which is the
documented pattern (`docs/Main_App/testing.md`, "run from a laptop against a
running house") stretched to the one machine that actually had everything
already in place. 226 QA checks total now (139 platform, 87 Todo's own).

**Phase 7 is complete — 15 of 15.** `docs/Main_App/subsystems/todo-build-brief.md`
said to delete itself once the build finished, and it is gone.


---

## 2026-08-07 (later) — the house speaks, and the observe pass that was skipped

Asked two things: *"did you add example tasks on the board and see it to
completion to know it is all working well?"* and *"build the TTS capability into
the home base app."* The first was the more important question.

**The honest answer was no, and Story 41 had been marked Complete anyway.** The
87 browser tests were real, but they create a task, assert, and delete it inside
a headless browser — nothing had ever been *watched*. §13.4 lists four things
that must be seen before the phase is Complete, and the database settled it
plainly: **0 live tasks, 0 sound deliveries ever.** The chime heard the previous
night was the host script run by hand, not an alarm that travelled the pipeline.
Recording this because the mistake was not in the testing — it was treating a
green suite as sufficient, which is precisely the distinction the status
vocabulary in CLAUDE.md §0 exists to prevent, applied to the one story whose
whole job was to enforce it.

**All four are now observed**, with three real tasks seeded and kept (bins, water
filter, boiler service — a family's board, not test litter): the wall
screenshotted showing "Take the bins out" in red as overdue alongside the other
two and the Open now / heatmap / House health widgets; `send_reminders()` run for
real producing `Delivery(channel="slack", status="sent")`; and a **speech** alarm
synthesised, written to the bind mount as `36.wav`, and played by the host timer
through the 24"'s speakers.

**Groq Orpheus went in behind Story 38's TTS seam, and no call site changed** —
which is exactly what that seam was built for. Story 38 shipped a stub that
raised and stopped there on purpose; this is the vendor it was waiting for.

`nora_home/notifications/speech.py` is the published API: `speak("the bins go out
tonight")`, callable from any app. It exists rather than letting apps reach for
the provider because three things sit between text and a noise in the kitchen and
only one is synthesis — quiet hours are house-wide (the sound comes out of the
24" for whoever is in the room), and the audio has to reach the *host*, since the
speakers are on the Pi's HDMI and Django runs in a container with no path to
them. An app calling the provider directly would get correct audio, inside a
container, at 3am, that nobody would ever hear.

The **text** travels in `Notification.context`, never the audio: that field is a
`JSONField` and raw WAV does not survive the round trip — the same reason
`SoundChannel` already re-resolved a task's alarm on delivery rather than
carrying bytes. So synthesis happens in the worker, and `SoundChannel` now has
two sources, `alarm_task_id` and `speech_text`.

Groq because it needs no local model, no GPU and no audio toolchain on the Pi:
HTTPS in, WAV out — WAV specifically because the host's `aplay` plays it
natively and an MP3 would mean installing a decoder for one path. With
`NORA_HOME_TTS_PROVIDER=none` (the default) the house still boots and still
reminds; only spoken alarms go quiet.

**And the feature surfaced a bug worth more than itself.** `env()` reads the real
environment, Compose passes every `.env` value into the container, so on the Pi
`./nora test` inherited the live `NORA_HOME_TTS_PROVIDER=groq` and **made a
billable API call to synthesise speech inside a unit test.** It surfaced only
because two tests asserting the *degraded* path started failing with genuine WAV
bytes — had they been written any looser it would have been silent, and the suite
would have been quietly spending money and requiring network on every run, which
is not the thing CLAUDE.md §2.4 promises. `config/settings/test.py` now forces
the TTS, Groq and Anthropic credentials off rather than leaving them unset, and a
test asserts it so the next key added cannot reopen the hole.

927 tests green.

---

## 2026-08-07 (later still) — a missing mouse pointer, and the bug behind it

Reported as one oddity about the pointer on the 24": invisible over the main
body after the **kiosk** drove the wall somewhere, visible over the sidebar at
the same time, and visible everywhere when navigating on the 24" **itself**.
Three behaviours, so the question was which pair to explain. Both were bugs.

**The pointer.** `:root[data-surface="wall"] body { cursor: none }` dated from
when the wall was a passive ambient view nobody pointed at. It is the real app
now and gets driven from its own sidebar, so hiding it outright means aiming
blind. It also hid *inconsistently*, and that is the part worth keeping:
`cursor` is inherited, and **an inherited value loses to any directly-declared
one — including the browser's own `a:link { cursor: pointer }`.** So the
pointer vanished over the page body and came back over every link. Now hidden
only while the mouse is still (4s), cleared on the first move, which is what a
video player does and for the same reason. The rule needs `body, body *` to
beat those link and `.card` declarations rather than merely inherit past them.

**The surface.** The wall shows the real app through an iframe, and the app
inside is fetched at its own ordinary URL, so `Sec-Fetch-Dest: iframe` plus a
referer naming the wall's shell is what promoted it to `wall`. **Only the first
hop carries the shell as its referer.** Click a link inside the iframe and the
referer is the previous *app* page, the check missed, and detection fell all
the way back to User-Agent: the 24" rendered at laptop type scale with its zoom
dropped, silently, until the kiosk drove it again. Any same-origin iframed
document now counts, which covers every later hop.

Proved before changing anything, because the middleware puts the answer on
every response as `X-Nora-Surface`:

```
Referer=/home/displays/wall/  -> wall        # kiosk-driven, the case that worked
Referer=/todo/                -> desktop     # a click on the 24", the bug
```

and again after, with two guards that must not move — a laptop clicking a link
(`Sec-Fetch-Dest: document`, same-origin referer) stays `desktop`, and another
origin iframing the house stays `desktop`.

**This is the second time a wall-scale bug has been invisible to the whole test
suite and obvious on the glass** — after `--nav-width: 244px`. The pointer was
the only reason anyone noticed: it is the one thing that behaves differently
between `wall` and `desktop` *without* being a size, so it made a silent
surface change audible. Nothing else about a wall rendering at laptop scale
announces itself.

Seen on the hardware, not inferred: `scrot -p` over the wall's main body with
the mouse moving (pointer drawn) and after 7s still (gone), the same pair over
a sidebar link — where the hover highlight stays lit under a hidden pointer,
which is exactly the combination the old rule could not produce — and the
System page reached **by clicking the wall's own sidebar**, still at full wall
type scale.

940 tests green (+3: the in-iframe hop, the two guards, and a stylesheet check
that no `cursor: none` escapes the idle flag).

---

## Next

1. **Living background: check it holds up over hours, not just minutes.**
   Verified live on the physical wall and kiosk the same session (real
   weather, both screens in sync, no regression to the kiosk remote-control
   flow), and the light theme is now checked on real hardware too (see the
   invisible-text fix above) — what's still not checked is continuous motion
   (rain/snow/stars, backdrop blur on every pane) holding up over hours
   rather than minutes on a Pi 5 driving two Chromium instances at once.
2. **Story 24 — house maintenance**, the first real app, which is what proves the
   skeleton was worth building. Unblocked since Story 27 (2026-08-02). Its
   `requirements.md` needs the user's approval before any code is written — the
   first of DEVELOPMENT.md's three gates. It also has to settle what replaces
   the tracker's `register_trackable()` for house apps, which Story 40 removed
   without a successor (see the 2026-08-06 entry).
3. **Story 41 — Todo: tests, docs, deploy.** Unblocked by Story 40. Browser
   tests through `./nora qa`, and the deployed-and-observed pass that moves the
   whole phase from built to Complete.

---

## 2026-08-09 — Phase 8 designed: a UI/UX overhaul, and an interactive mockup

Asked for a ground-up UI/UX redesign — explicitly not a CSS pass. Analysis was
done against the **running house**, not the code: every page captured from the
Pi at desktop, phone, kiosk and wall sizes, plus a screenshot of the physical
screens. That is what produced the findings, and several of them were invisible
in code review.

**What the live capture showed.** The 24" wall was ~65% empty. Todo's board held
two cards in four fixed-height columns. Settings used the left half of a 1440px
screen. The kiosk filled its top 45% and carried registry categories — "House",
"This house", "System" — as tile subtitles. Every primary action (Add a widget,
Rearrange, Switch profile, Theme) was hidden inside the avatar dropdown. On a
phone the desktop rail rendered as a full-width centred text stack *between*
content blocks, and "Change the water filter" clipped to four stacked words in a
60px column. Todo — the Level 2 app the platform leans on — sat under **SYSTEM**,
below Integrations, with "Settings" appearing twice in the same sidebar. And the
Almanac scene, the house's entire visual identity, rendered as flat near-black.

**The diagnosis was one thing, not a list**: a single layout — sidebar plus card
grid — stretched across five surfaces by a zoom multiplier. Notably that is the
exact template §4 already rejected once in mockups, and then got built anyway.

### The mockup, and why it is now the reference

`docs/Main_App/ui-overhaul-mockup.html` — standalone, interactive, no server and
no build. It is now the **UI/UX reference**: future changes go into it first, are
shown, and are approved before any production code. Recorded in §0's update table
and §4.

A picture could not have settled the questions that actually arose. Whether a
rearranged dashboard still tiles cleanly, whether the kiosk survives twelve apps,
whether text holds up at noon in the rain — all behavioural, all answered in a
browser in seconds.

**Making it trustworthy cost four rounds of correction, and that is the lesson.**
Four separate lists in it turned out to be invented rather than read:

| Invented | Reality, once queried |
|---|---|
| Kiosk controls ("Mark first done", "Mute an hour") | `wall-live.js` implements exactly three actions — `navigate`, `refresh`, `banner`. **Every control is a path.** Todo's five are verbatim from its `apps.py`; no other app declares any |
| Widgets "Outside" and "Alerts" | Not widgets. Weather is an integration feeding the scene; alerts are a page. The real catalogue is ten, across three apps |
| An Apps directory listing Todo, Alerts, Measurements… | `app_directory` lists **house apps only** and filters to `nora_has_page`. Todo is excluded by design. It is legitimately empty until Story 24 |
| Nav items Maintenance, Numbers, "All apps" | Maintenance does not exist; the real title is **Measurements**; **Integrations** is a registered app I had omitted entirely |

Each was fixed by querying the running app or reading `settings.py`, never by
reasoning about it. **A mockup showing plausible content is worse than none** — it
gets approved, then built.

### Four class collisions, none of which raised an error

Building it surfaced a bug class worth carrying into Story 45 as a test:
`.who` (member name vs task assignee), `.cap` (caption vs fader knob), `.bar`
(the prototype's own control bar vs the vitals track), plus a near-miss on
`.body`. In every case a later `@layer` silently won and the component rendered
as something else — a name became a 20px orange circle; every caption in the app
became an absolutely-positioned knob. **No console error in any of them**; all
four were found by looking at a screenshot.

The first audit script missed `.bar` because it only captured the *first* class
in a selector, so `.vit .bar` never registered as a use of `.bar`. Fixed matcher
now reports nine cross-layer names, all verified as legitimate parent-scoping
(`.card-h .sub` vs `.hkey .sub`) or modifiers (`.task.done`).

Two other bugs worth remembering because they will recur in production CSS: a
**colour cannot be a layer in a comma-separated `background` list**, so
`background: var(--veil), linear-gradient(…)` is invalid and the browser drops
the whole declaration — the veil vanished on every surface at once; and **`vw`/`vh`
inside a transform-scaled container resolve against the viewport**, not the
container, so a sun's halo rendered ~160px wide inside a 1440px frame.

### What was decided

Dark only, arc-reactor identity. **Two layouts, not three** — Work (phone →
desktop → wall) and Control (kiosk); the wall is the desktop one ramp up. Widget
**size variants S/M/L/XL** on a 12-column grid with `dense` and
`minmax(--row, 1fr)`, which is what removes both the ragged holes and the empty
lower half. Scene reduced to time and weather. The kiosk rebuilt as a **hardware
control desk** — rotary encoder, numbered key bank, faders, dot-matrix readout —
after the first two attempts were rejected as unscalable and then as ugly.

IA follows one rule, *Home is the base app and everything else is an app*: Status
+ Log merge into **System** (a page of Home, not an app), the Apps directory is
deleted in favour of a ⌘K palette, and only the four `nav=True` apps are called
apps.

### Recorded

Dashboard: **Phase 8, Stories 43–55**, phase bar, and counts (42 → 55 total,
planned 10 → 23). Cards are hand-authored per phase — the `STORIES` object only
feeds the modal — so adding a story means editing both, which cost a wrong-place
insertion before it was caught. CLAUDE.md §4 carries the four reversals, and §0
now lists the mockup as a required update.

**Nothing is built.** Story 43 is the entry point precisely because it ships zero
visual change: it isolates pipeline risk from design risk and reports a measured
arm64 build time before nine other stories depend on it.

Also fixed in passing: `.claude/launch.json` pointed at `.venv\Scripts\python.exe`
— a Windows path, on a Mac — so the dev server had never been startable on this
machine.

**Decided the same day: the front end is a rewrite, not a migration.** The
mockup is the reference and production is rebuilt from it — `static/nora_home/css/*`
and `js/*` deleted, templates keeping their Django logic and losing their markup.
The deletion happens at Story 45, so Story 43 is the last point at which the old
front end still exists. Story 55 rewrites the QA suite rather than adapting it:
its 226 checks select by class names that will not survive. Two things are kept
because they are not styling — `zoom.py` writing `style="zoom:"` onto `<html>`,
and the `data-surface` / `data-daypart` / `data-weather` attributes.

---

## 2026-08-09 — the documentation stops being a copy

Asked how a change propagates so the docs and the code cannot drift. The answer
was not a rewrite: **length is not what makes them cumbersome, duplication is.**
Two proofs were already in the repo.

`register_trackable()` — the call `DEVELOPMENT.md` tells a house-app author to
make — appeared in **five documents and zero lines of Python**. Story 40 deleted
the app that published it; the documentation went on promising it because
nothing ever executed the promise. And `cross-functionality.md` says of itself
that signatures are *"copied from the code, not from memory"*, which is a
hand-maintained mirror and therefore a rot vector by design.

Three things built, cheapest and highest-value first.

### 1. The contract is executable

`tests/contract_app/` is a real house app — declaration, `urls.py`, views, one
widget — declared exactly as `DEVELOPMENT.md` describes.
`tests/test_app_contract.py` installs it via `override_settings` and asserts it
reaches **every** surface: `navigation()`, its own URL, every declared section
(200, not merely resolvable), every kiosk control, and the widget picker. One
test asserts the strongest form of the claim — that nothing in `nora_home/`,
`config/` or `templates/` names the app at all.

Installed by override rather than added to `config/settings/test.py` on purpose:
it is a fixture, not a shipped reference app, and the old reference app was
removed deliberately. It has no models, because Django will not migrate an app
added after the test database is built and nothing in the contract needs tables.

**Verified by breaking it, not by watching it pass.** A section pointed at a
missing path failed both the section and kiosk assertions; `nora_nav = False`
failed the navigation assertion; a mistyped widget path failed the widget
assertion. Restored, green. A test written and never seen to fail proves nothing.

### 2. The recipe points at the executable version of itself

`DEVELOPMENT.md`'s "Ten-minute start" now opens by pointing at `tests/contract_app/`
as the working minimum. The instructions and the fixture are the same thing, so
the recipe going stale is a red suite.

### 3. Derived tables are generated

`manage.py sync_docs` rewrites the blocks between `<!-- sync_docs:begin ... -->`
markers from the registry and the published `api` modules — the installed-apps
table, every public API signature with its real arguments, and the full
`NoraAppConfig` declaration table. `--check` writes nothing and exits non-zero
on drift; `tests/test_docs_in_sync.py` runs it.

**One bug found immediately, and it is the reason the determinism test exists.**
The app-contract table was stale the instant after writing it: `repr()` of a
`property` object embeds its memory address, so `nora_home_metadata` produced a
different row every run and `--check` would have been permanently red. Data
fields only now, and a second test asserts every generator returns the same
bytes twice.

Suite: **952 passing**, 21 skipped, ~5s.

### What was deliberately not done

No doc rewrite for brevity, and no visual-regression baselines. The rewrite
should follow the tooling — it is only now clear which text is derivable — and
Phase 8 invalidates a large slice of §4 on its own. Baselines against a design
still changing daily would be noise.

---

## 2026-08-09 — Phase 8 made startable, and the dashboard stops contradicting itself

### The dashboard was duplicating the thing it exists to track

Ten story cards disagreed with the `STORIES` object they point at — 28–33 and
42 showed **Planned** while the data said `complete` — and the summary claimed
25 complete against an actual 32. Nobody mistyped anything; the second copy
simply stopped being updated, which is what second copies do. In the document
whose whole job is tracking work.

Status now has one home. The cards keep their hand-written descriptions and
tags, because those are presentation, but their badge and colour are stamped
from `STORIES` on load and the summary counts are counted rather than typed.
Verified: **0 cards disagreeing**, counts 32 / 6 / 0 / 20, total 58.

Also fixed a stray `</div>` sitting *after* `</html>`, left by the earlier
Phase 8 insertion. It rendered fine, which is exactly why it survived.

### Auditing the mockup against the stories

Every distinct thing in `ui-overhaul-mockup.html` was checked against Phase 8's
sixteen stories. Two genuine gaps, both now closed:

- **Scrolling the wall.** Story 51 promised three new capabilities — zoom,
  wall-only power, volume. The mockup's bend wheel is a fourth, and there is no
  scroll message in the bus at all: `wall-live.js` implements `navigate`,
  `refresh` and `banner`. Added, with the detail that matters — the wheel is
  spring-centred, so it sends a **rate**, not a position, and the wall
  integrates it.
- **The Picker.** The kiosk's vertical app scroller and the phone's horizontal
  rail are the same control rotated, and nothing named it as one component.
  Now part of Story 45, carrying the two traps it must survive: `scroll` does
  not bubble, so the listener has to be in the capture phase; and the
  programmatic centring must be flagged or it reads back as the user choosing
  something and fights itself.

A third flag — Pi vitals — was a false positive from a too-literal pattern.
Story 52 covers it.

### Ready to start

- **No node on this Mac.** That settles Story 43's shape rather than leaving it
  a preference: the build has to run in a Docker stage.
- The Dockerfile is already multi-stage (`base` → `builder` → final), so a node
  stage fits the existing structure.
- **4,213 lines** of CSS and JS under `static/nora_home/` are what Story 45
  deletes.
- The Pi answers, reports `aarch64`, and all services are healthy — so Story
  43's arm64 build-time measurement can actually be taken rather than guessed.

Story 43 is marked **next**. It ships zero visual change on purpose: it isolates
pipeline risk from design risk and returns a measured build time before nine
other stories depend on it.

## 2026-08-09 — Story 43: the build pipeline, and the numbers it was meant to produce

Vite 7 + Tailwind v4 + Alpine 3 behind `django-vite`, shipping the **existing**
UI unchanged. Zero visual change was the deliverable, and it holds: the Todo
board, the home dashboard and the kiosk all render exactly as before, through
hashed files, with an empty console.

**Measured on the Pi, arm64, node in a container** — the number nine other
stories were waiting on:

| | |
|---|---|
| `npm ci` | **15s** (34 packages) |
| `vite build` | **1.75s** (19 modules → 18 entries, 476 KB) |
| Tailwind v4 on arm64 | resolved; `nh-next.css` built at 7.15 kB |

The fallback (build on a laptop, commit `dist/`) was never needed. The output is
committed regardless, so a fresh clone with no network still boots and the Pi's
runtime image stays node-free.

**Sources moved to `assets/`.** `static/` now holds only generated or vendored
files. Story 45's deletion of the old front end is a single directory.

**One entry per file the templates already load**, not a bundle. The kiosk does
not load `todo.css`; merging entries would have changed the cascade on surfaces
nobody looks at.

### Three bugs, all of which rendered wrong rather than raising

- **CSS entries went out as `<script type="module">`.** `{% vite_asset %}` emits
  a script tag for *every* entry, and Vite treats a `.css` entry as an entry.
  Chrome refused all six on MIME type and the house rendered as unstyled black
  text on black. Found by looking at the screen; the suite was green at the
  time, because every page still returned 200 with a resolved URL on it. CSS now
  goes through `{% vite_asset_url %}` inside a real `<link>`, and
  `test_stylesheets_are_never_emitted_as_scripts` fails on the other form.
- **`django-vite` ships a top-level `tests` package into site-packages.** A
  regular package beats a namespace package regardless of `sys.path` order, so
  it shadowed this repo's `tests/` and all ten app-contract tests died with
  `ModuleNotFoundError` — the day after they were written to catch exactly this
  kind of silent breakage. `tests/__init__.py` closes the class, not the case.
- **I wrote `/home/screens/kiosk/` and `/home/screens/wall/` from memory** into
  a new test. Both are wrong (`/home/displays/…`). A test that 404s proves
  nothing and looks like it proves something. It uses `reverse()` now. Same
  failure as the mockup's five invented lists; the fix is the same — resolve it,
  never recall it.

### Verified

- 963 tests green, including 12 new ones treating the manifest as the contract:
  every entry a template asks for is built, every built file exists, every
  source file is an entry, `dist/` is committed, `node_modules` is not.
- Every page fetched and every asset it references served: 19 files, all 200,
  across home, all six Todo pages, the house log, the kiosk, the wall and the
  switcher.
- `collectstatic` under the **prod** storage backend
  (`CompressedManifestStaticFilesStorage`) — 562 files post-processed, source
  maps resolved, django-vite's URLs going through `staticfiles_storage.url()`
  and picking up the double-hashed names.
- Globals survive the move to ES modules: `NoraHome.post` and `NoraHome.say` are
  still there. Every file was already an IIFE talking through `window`, which is
  why the conversion cost nothing.

### Not yet

The Pi has built the assets but has **not run this commit**. The Dockerfile's
node stage, and both screens rendering through it on the real hardware, are
unobserved. Story 43 stays *built, unproven* until they are.
