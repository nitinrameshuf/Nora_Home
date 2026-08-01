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

---

## Next

1. **Story 23 — design system.** Blocked on a decision between the directions in
   `design-options.html`.
2. **Story 27 — first real run on the Pi.** The highest-value story on the board: it
   converts eight *built, unproven* stories into either *complete* or a bug list.
3. **Story 24 — house maintenance**, the first real app, which is what proves the
   skeleton was worth building.
