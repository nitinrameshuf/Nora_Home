# BUILD BRIEF — Todo

**Scaffolding, not documentation. Delete this file when the build is finished.**

**Who this is for:** whoever implements Todo. Written by a model with the whole
codebase in context so the implementer does not re-derive any of it. Every
decision is already made.

**The design is [`todo.md`](todo.md).** Read it first — it is the *what*, and it
is approved. This is the *how*: order, files, traps.

**If this brief contradicts the code you find, the code wins.** Stop and say so
rather than guessing.

---

## Ground rules

1. **No npm, no bundler, no framework.** The Pi never runs a build. Third-party
   JS is vendored as a single file into `static/nora_home/vendor/`. ECharts and
   Gridstack are already there.
2. **No app reads `os.environ`.** Add the setting to `config/settings/base.py`
   with a default, read it via `django.conf.settings`.
3. **Every model inherits a base from `nora_home/core/models.py`.**
4. **Migrations are source.** Generate once, commit, never edit an applied one.
   The Docker entrypoint runs `migrate` on every web start.
5. **Failures degrade, never cascade.** A card that raises renders "unavailable".
   Object storage down means no photo, not no task.
6. **Docs ship in the same commit as the code** — see Phase 13.
7. **Comments explain why, not what.** Match the density already in the file.

## Traps that have already cost this project real time

- **`ready()` must contain imports only.** Anything touching the database there
  runs before migrations and breaks `manage.py migrate` on a fresh install.
- **Do not set `default = True` on an AppConfig.** `NoraAppConfig.__init_subclass__`
  does it. Getting this area wrong once produced a silently empty registry.
- **Django's `{# #}` comments are single-line.** A multi-line one renders as
  visible text on the page. Use `{% comment %}`.
- **URL patterns resolve in declaration order.** `<slug:slug>/command/` declared
  before `wall/<slug:slug>/` made an endpoint silently unreachable. Put literal
  prefixes before variable ones.
- **The Docker entrypoint prepends `python manage.py`** to unrecognised args.
  Passing the full command doubles it.
- **A container keeps the environment it started with.** After editing `.env` it
  is `./nora recreate`, never `restart`.
- **`env_file` passes values literally.** A quoted secret in `.env` arrives with
  the quote characters attached.
- **Renaming a Celery task leaves an orphan in the beat database.**
  `django_celery_beat.DatabaseScheduler` syncs *into* the DB and never removes
  entries whose task is gone; the orphan raises `KeyError` every interval,
  silently. `prune_beat_schedule` runs at beat startup and handles it — but do not
  rely on that as an excuse to rename carelessly.
- **The test suite is hermetic** (`config/settings/test.py`): SQLite, in-memory
  channel layer, eager Celery, no environment, no network, no credentials. A test
  needing any of those will pass on a laptop and fail on the Pi.

---

# Phase 0 — Clear the ground

**0.1 Levels.** Add `nora_level: int = 3` to `NoraAppConfig`
(`nora_home/core/registry.py`) and surface it on `AppMetadata`. Platform apps
declare 1, Todo declares 2.

**0.2 The dependency test.** `tests/test_house_apps.py` currently forbids
importing *any* other app's models. Replace with a directional rule: nothing at
Level 1 or 2 may import Level 3. Level 3 may import Levels 1 and 2 through their
published APIs.

**0.3 `uninstall_app`** warns loudly and names what breaks when removing a Level 2
app.

**0.4 Delete `houseapps/example_habit/`** — the whole directory, its
`docs/House_Apps/example_habit/` folder, and its entry in `.env`. Already agreed.

**0.5 Delete `nora_wall_panels`** — the field on `NoraAppConfig`, the
`wall_panels()` function, the `wall_panels` entry on `AppMetadata`, the contract
test in `tests/test_house_apps.py`, and its section in `DEVELOPMENT.md`. It is
dead code: nothing renders it.

**Verify:** `./scripts/run-tests.sh` green, `manage.py check` clean.

---

# Phase 1 — Models

Create `nora_home/todo/` with the standard Django layout plus `api.py`,
`analytics.py`, `scheduling.py`, `recurrence.py`, `mcp_tools.py`.

**1.1 `apps.py`:**

```python
from nora_home.core.registry import Category, NoraAppConfig


class TodoConfig(NoraAppConfig):
    name = "nora_home.todo"
    label = "todo"
    verbose_name = "Todo"

    nora_slug = "todo"
    nora_title = "Todo"
    nora_description = "Everything that has to happen, when, and who hears about it."
    nora_icon = "check"
    nora_category = Category.SYSTEM
    nora_level = 2
    nora_order = 5
    nora_url_prefix = "todo/"

    nora_widgets = [...]           # Phase 7
    nora_kiosk_controls = [...]    # Phase 6
    nora_provides_mcp_tools = True

    def ready(self):
        from nora_home.todo import mcp_tools, signals  # noqa: F401
```

**1.2 Models**, exactly as §3 of the design doc: `Task`, `Instance`, `Event`,
`Label`, `Comment`, `Attachment`, `Link`, `Reminder`, `ChangeEvent`,
`TodoPreference`.

Notes that matter:

- `Task.priority` — choices 1/2/3, **no default**. The form must not pre-select.
- `Task.owner` — required. May differ from creator.
- `Instance.outcome` — `pending` / `done` / `missed` / `skipped`.
- `Instance.skipped_at` — model-level validation that it precedes `due_at`.
- `Comment` and `Attachment` attach to **either** a task or an instance. Two
  nullable FKs with a constraint that exactly one is set is simpler here than a
  generic relation, and far easier to query.
- `ChangeEvent` — `field`, `from_value`, `to_value`, `at`, `by`, `reason`. Write
  one on **every** reschedule, priority change, label change, skip and archive.
  See §13 of the design doc for why this is not optional.
- **No counter fields anywhere.** No `times_moved`, no `streak`, no
  `completion_rate`. Every statistic is computed on read (§13).

**1.3** Copy `nora_home/tracker/escalation.py` into the new package, repointing
its imports. Leave the tracker in place for now; it is deleted in Phase 12.

**1.4** `makemigrations todo`, `migrate`, commit the migration.

**1.5** Register everything in `admin.py`.

**Verify:** migration applies on a fresh database; `manage.py check` clean.

---

# Phase 2 — Recurrence and instances

**2.1 `recurrence.py`** — parse and evaluate rules. Fixed (weekday, monthly,
interval-from-a-start-date) and rolling (N days after last completion). One
function: given a task and a point in time, return the next due moment.

**2.2 `scheduling.py`** — materialisation. Carry over
`nora_home/tracker/scheduling.py`, which already does the rolling-window
correctly.

- **Fixed** recurrence: materialise ~90 days ahead.
- **Rolling**: exactly one open instance; create the next on completion.
- A one-shot task gets exactly one instance.

**2.3 Two Celery tasks**, both registered in the beat schedule the way existing
platform tasks are:

- `extend_windows` — nightly. Extends the 90-day window for fixed recurrences.
- `close_passed_instances` — every few minutes. Marks `pending` instances whose
  `due_at` has passed as `missed`. **This job is the only reason missed days
  appear in any chart.**

**2.4** `tests/test_scheduled_work.py` asserts every scheduled task imports, is
registered, and routes to a consumed queue. Both must satisfy it.

**Verify:** unit tests covering fixed vs rolling, window extension, missed
closure, and that completing an instance retroactively does not disturb the
current one.

---

# Phase 2a — Shared tasks and approval  (Story 42) — **BUILT 2026-08-05**

Landed as specified below, plus three details the spec left open — see
[`todo.md`](todo.md) §4a "As built". Phase 3 must render `awaiting_approval`
(it belongs in neither the open columns nor the done ones) and must scope every
board query through `api.tasks_for()`.

It arrived after Phases 1 and 2 had already shipped, so it is a follow-up
migration rather than a change to the original models — but the board renders
assignees and the approve/reject actions, so building Phase 3 first would have
meant building it twice.

Design: [`todo.md`](todo.md) §4a, which is approved. Do not re-derive it.

**2a.1 Model changes** (`nora_home/todo/models.py`, plus a migration):

- `Task.assignees` — M2M to `AUTH_USER_MODEL`, blank. Who *can do it*.
  `Task.owner` is untouched and still means who is *responsible*.
- `Task.approver` — nullable FK. **Its presence is the approval requirement**;
  there is deliberately no separate mode flag to keep in sync.
- `Instance.outcome` — add `awaiting_approval`.
- `Instance.approved_at` / `approved_by`.

**2a.2 Recurring tasks cannot have an approver.** Enforce in `Task.clean()`,
and add a `CheckConstraint` so it holds at the database level too — a rule that
only lives in application code is a rule that a management command or a data
import will quietly break.

**2a.3 The transitions**, in `api.py`:

```
pending ──complete──▶ awaiting_approval ──approve──▶ done
                             │
                             └──reject (reason required)──▶ pending
```

With no approver, `complete` goes straight to `done` — same call, no branch for
the caller to remember.

**Rejection's reason is required, not optional.** Write it as a `ChangeEvent`
(`field="approval"`, `to_value="rejected"`, `reason=...`) so it lands in the
same history as every other change. "No" with no reason is what makes an
approval workflow resented.

**2a.4 Scoping.** Anywhere tasks are filtered to a person, the rule becomes
`owner in members OR assignees intersects members`. Use `.distinct()` — the
M2M join will duplicate rows otherwise, and a board showing the same card three
times is exactly the kind of bug that looks like a rendering fault.

**2a.5 Effort splits, never multiplies.** A 60-minute task with three assignees
contributes **20 minutes to each** person's load. Put this in one function now
even though Phase 7 is what consumes it, so there is one place to be right.
Counting it in full three times would tell three people they each have a full
day of what is really one hour of house work — and the scheduling suggestions
are built directly on that number.

**Verify:** any assignee can close a shared task; a task with an approver
cannot reach `done` without one; rejection returns it to `pending` and the
reason is retrievable; a recurring task refuses an approver at both the model
and database level; a shared task appears once — not once per assignee — on
each of their boards.

---

# Phase 3 — The board — **BUILT 2026-08-05**

Landed as specified below. See [`todo.md`](todo.md) §6 "Tasks — as built" for
two things settled while building it: the `awaiting_approval` strip, and a
one-shot task's `Task.state` now following its instance to `done`. Also fixed
a genuine platform bug in `nh-app.js`'s `post()` helper — see the same section
— found only by driving the board in a real browser, which every future phase
touching the front end should keep doing rather than trusting the unit suite
alone for this class of bug.

**3.1 `urls.py`** — `app_name = "todo"`, mounted at `/todo/`. `RESERVED_SLUGS`
already prevents prefix collisions. Literal segments before variable ones.

**3.2 Views** — board, task detail, create, edit, archive, restore, complete,
uncomplete, skip, delete. All `@login_required`; all mutating views `@require_POST`
and CSRF-protected.

**3.3 Templates** — four columns (Priority 1 · 2 · 3 · Archived), live counts,
cards carrying title, due, labels, recurrence marker, comment count, alarm marker.
Match the reference screenshot's information density.

**3.4** Scope with `scope_members(request)` — never `request.user` directly. That
is what makes the Everyone toggle work for free.

**3.5 No drag-and-drop.** Priority is set at creation and changed by editing.
Archiving is a button.

**The CSRF trap:** front-end mutations must go through `window.NoraHome.post()`,
which supplies the token, and **must check `response.ok`**. `fetch()` does not
reject on a non-2xx — "Add a widget" was silently 403ing for a day while the page
looked like it had worked.

**Verify:** create, complete, archive, restore, delete — each surviving a reload.

---

# Phase 4 — Reminders and notifications — **BUILT 2026-08-05**

Landed as specified below, plus the escalation engine's port from the tracker
(§9 said "carried over... largely intact" — Instance's escalation bookkeeping
fields have sat unused since Story 30 waiting for exactly this). See
[`todo.md`](todo.md) §8/§9 "as built" for what changed in the port: no second
`EscalationEvent` table (reuses `ChangeEvent`), escalation's audience is always
the owner alone (never assignees — that's reminders' job), and an
`acknowledge()`/"Seen it" action, new UI over fields that already existed.

**4.1 `Reminder`** evaluation: relative offsets everywhere, absolute on
non-recurring tasks only. A task given a due date gets one automatically.

**4.2** Per-member default due hour (09:00) in `TodoPreference`, for date-only
tasks.

**4.3 Routing** — the table in §8 of the design doc. Priority 1/2/3, reminder vs
escalation, personal vs family channel vs each member.

**4.4 Quiet hours** — use what exists. Slack follows the member's
`HouseMember.quiet_hours_*`; sound follows house-wide
`notifications.quiet_hours`. Do not invent a third mechanism.

**4.5** Fire once. No snooze.

**4.6** A Celery task scanning for due reminders. Every reminder send carries a
`dedupe_key` — `notify()` and `notify_house()` both honour it and return `None`
when suppressed, which is success, not failure.

**Verify:** a reminder fires once and only once; quiet hours suppress the right
channel and not the other; archived tasks produce nothing.

---

# Phase 5 — Calendar — **BUILT 2026-08-05**

Landed as specified below. See [`todo.md`](todo.md) §6 "Calendar — as built"
for what building it settled: "actual" means every non-`pending` outcome, not
just `done` (a missed or skipped instance is real history); archived tasks are
excluded the same way reminders and escalation already exclude them, but a
`done` one-shot task's own instance is not, since it's the record of the day
it happened; and an out-of-range month falls back to today instead of a 500.

Month view only, hand-written as a CSS grid. Shows events, plus **planned** and
**actual** instances in distinguishable weights.

Rolling recurrences show only their next occasion — say so in the UI rather than
letting it look like a bug.

---

# Phase 6 — Search, labels, kiosk — **BUILT 2026-08-05**

Landed as specified below. See [`todo.md`](todo.md) §7 "as built" for
`search_tasks()`/`FilterParams`/`SavedFilter`, §6 Labels "as built" for the
live-count fix and the new label-creation form, and §6 "The 10.1" kiosk — as
built" for why only 3 of the documented 5 kiosk controls are declared today
(Reporting and System tasks don't have pages yet — Stories 35/36).

6.4 turned out to already be done: the kiosk's two-level system was already
generic, driven entirely from the registry, from when the kiosk-drives-wall
redesign shipped. Todo's `nora_kiosk_controls` declaration needed zero
platform-level changes — confirmed by clicking through it on a real running
house, not just reading the code and assuming.

**6.1** Full text across titles, descriptions and comments. Combinable filters,
saveable and returnable.

**6.2** Labels page: every label with a live count; selecting one filters.

**6.3 Kiosk controls** — `nora_kiosk_controls` is `{title, path}` pairs only. The
kiosk navigates the wall; it cannot post back to an app. Todo declares: Tasks,
Due today, Calendar, Reporting, System tasks.

**6.4 The kiosk's top level must reach the whole house** — every platform section
and every installed app, not just the current one. Check what
`nora_home/displays/views.py: kiosk()` renders today; it derives tiles from
`navigation(role)` plus the hardcoded "This house" group. Extend it so nothing in
the house is unreachable from the panel, and so the Everywhere level is always one
tap from an app's own controls.

---

# Phase 7 — Analytics and Reporting

**7.1 `analytics.py`** — one documented function per metric, all computed from
history on read. **This module is the AI-readiness contract** (§13): the charts,
the MCP tools and any future AI layer all call these same functions.

**7.2** Every chart in §10 of the design doc — **including its Visual discipline
table, which is not decoration.** The platform's own home dashboard currently
breaks all six of those rules on one screen; go and look at it before building
this page. In particular: never render an axis for a series with no data, size a
card to its content, and keep every card on one aligned grid.

**7.3 Tone presets** — Calm / Standard / Competitive, in `TodoPreference`, with
individual overrides. Standard is the default.

**7.4 Widgets** — subclass `ListWidget` / `StatWidget` / `ChartWidget` from
`nora_home/dashboard/widgets.py`. `ChartWidget.option()` returns an ECharts option
dict; **do not set colours** — the house theme is applied client-side. Set
`wall_safe` honestly.

**No cached counters.** If anything is cached for speed, invalidate it when
history changes. A stale "19 of 30" after a retroactive edit is a bug nobody can
see.

---

# Phase 8 — System tasks

**8.1** `source=system` board inside Todo.

**8.2 Telemetry bridge** — a threshold breach, or an integration failing
repeatedly, creates a system task. One-directional: the measurement stays in
telemetry.

---

# Phase 9 — Slack

**9.1 Socket Mode container** — a fourth service beside `web`, `worker`, `beat`,
holding the outbound websocket. Needs the app-level token (`xapp-`) with
`connections:write`.

**9.2** One `/todo` command with subcommands (`ack`, `approve`, `new`, `help`
— decided 2026-08-06 over three separate commands, see todo.md §12), plus
Block Kit buttons —
Done · Skip · Snooze · Reassign.

**9.3** Confirm Slack's current concurrent-connection limits against their docs.

**Blocked until the workspace grants** `chat:write.public`, `im:write`,
`users:read`, `reactions:write`, and members have a `slack_user_id`. Build against
it; verify early. `SlackChannel` already maps Slack's unhelpful error codes to
actionable messages — extend rather than replace that.

---

# Phase 10 — Alarms

**10.1** Per-task alarm: chime, uploaded file (MinIO), or speech.

**10.2 TTS** — provider-agnostic interface, one stubbed implementation. **Stop at
the seam**; the provider is chosen later.

**10.3 Host playback** — a script run by a systemd timer, asking the container
what is due and playing it through the 24"'s HDMI audio. Same pattern as the
overnight screen schedule. Generated by `scripts/lib/provision-pi.sh`.

**10.4 Backlog cap** — after downtime, play the most recent only and collapse the
rest into one message.

---

# Phase 11 — Wall type scale, and the wall's own /home/ layout

**11.1 Type scale.** The wall shows the **real app** — the same board a laptop
shows — not a summary. `nora_home/ui/` already detects the surface; use it to set
a larger type scale, roughly 1.6×, applied through CSS custom properties.

**One layout, one set of components, one variable.** Do not fork the templates and
do not build wall-specific components. If a rule needs `data-surface="wall"` to do
anything other than change a size, stop and reconsider.

Verify by measurement, not by eye: text must be legible at three metres, and the
contrast floor of 4.5:1 still applies at every theme and daypart (Phase 13).

**11.2** `DashboardLayout.Surface.WALL` already exists, unused. It governs only
what the wall shows when pointed at `/home/`. Adopt it, and build an editor
reachable from a phone or laptop — the 24" has no input devices. The picker
respects `wall_safe`.

**11.3** The wall's boot destination is configurable, defaulting to the Todo
board.

---

# Phase 12 — Remove the tracker, add the House log — **DONE 2026-08-06 (Story 40)**

**12.1** Delete `nora_home/tracker/` entirely. Update `config/settings/base.py`,
`config/urls.py`, `config/celery.py`, `nora_home/core/signals.py`,
`nora_home/mcpserver/tools.py`, `nora_home/telemetry/widgets.py`, and
`bootstrap_home`. Move the three seeded escalation policies to Todo.

**12.2 House log page** — audit events, health snapshots, notification
deliveries, integration runs and telemetry threshold events on one timeline,
filtered by time / severity / source / subject, with charts. Under House in the
sidebar.

**12.3 Audit coverage** — `record()` has four call sites and three are being
deleted. Call it wherever a family member might later ask what happened: signing
in as someone, changing a setting, installing or removing an app, a backup
running, an integration failing, a task completed or escalated. **The page is
useless without this; they ship together.**

> **As built.** All of the above, plus scope changes. Two judgement calls worth
> keeping: setting changes carry the **new values** in `detail`, because "why did
> the wall go dark at six" is only answerable if the row says what the hours
> became; and `app.uninstalled` is written at *warning* severity when data was
> purged and *notice* when it was not, because unmounting an app and dropping its
> tables should not look like the same event on the timeline.
>
> The integration one fires on `consecutive_failures == threshold`, not `>=` —
> an integration polling every five minutes and down for a day would otherwise
> write 288 identical rows and bury everything else on the page.

---

# Phase 13 — Tests, docs, deploy

**13.1 Unit tests**, `tests/test_todo.py`. Hermetic. Fixtures already exist in
`tests/conftest.py` — `member`, `adult`, `admin_member`, `household`,
`make_member`, `series`, `signal_recorder`. Cover at minimum:

- Fixed vs rolling recurrence, and window extension.
- `close_passed_instances` marking misses.
- Skip before `due_at` succeeds; after it fails.
- Retroactive completion does not disturb the current instance.
- Every `analytics.py` function against a known history.
- Reminders fire once; quiet hours suppress the right channel.
- Archived tasks produce no reminder and no escalation.
- Routing by priority sends to the right audiences.
- A `ChangeEvent` is written on every reschedule, priority change and archive.

**13.2 QA tests**, `tests/qa/test_todo_qa.py`, `pytestmark = pytest.mark.qa`.

Two traps, both already paid for:

- **Never use `networkidle`.** Pages hold websockets and poll weather, so it never
  fires. Use the `visit()` helper.
- **Page actions live inside the profile dropdown** and are invisible until
  opened. Call `open_actions_menu(page)`.

Cover: the board renders and its actions survive a reload; the calendar renders;
Reporting renders with no "could not load"; no console errors; no horizontal
scroll at 390×844, 820×1180, 1440×900, 1920×1080, 1024×600.

**Contrast:** any new text must clear **4.5:1**, measured with
`measure_text_contrast` at **every theme × daypart combination** — a contrast bug
here was invisible for hours because it only appeared in daylight. **Do not use
axe-core's `color-contrast` rule**; it composites onto the DOM ancestor rather
than real pixels, and this app's glass panes sit over a live gradient. If a value
is short, fix the CSS by a measured sweep (the method is in
`docs/Main_App/testing.md`) — do not widen the threshold.

**13.3 Docs, same commit:**

- `docs/Main_App/subsystems/todo.md` — update anything the build changed.
- Delete `docs/Main_App/subsystems/tracker.md`.
- `docs/Main_App/architecture.md` — components, boundaries, Mermaid diagrams.
- `docs/Main_App/cross-functionality.md` — `nora_home.todo.api` signatures,
  copied from the code.
- `docs/Main_App/DEVELOPMENT.md` — Levels, and the removal of `nora_wall_panels`.
- `docs/Main_App/testing.md` — what the new tests cover.
- `docs/Main_App/progress.md` — a dated entry at the bottom.
- `docs/User/dashboard/nora_home_dashboard.html` — the `STORIES` object, summary
  counts, phase bars.
- `CLAUDE.md` — §2 state, §4 the Levels decision, §7 layout.
- **Delete this brief.**

**13.4 Deploy and observe.** `./nora upgrade`, then `./nora qa https://<pi>`, then
**see it with your own eyes over SSH**: the board renders on the wall, a reminder
arrives in Slack, an alarm plays through the 24"'s speakers, the wall shows the
chosen widgets.

Until all of that is observed the status is **built, unproven** — never Complete.

---

## Stop and ask rather than guessing

- The TTS provider.
- Anything that would change an approved decision in `todo.md`.
- Any git history rewriting. The repo is pulled on the Pi.
