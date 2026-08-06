# Todo — the house's task system

**Status: designed, approved, not built.** This document is the agreed design. It
replaces [`tracker.md`](tracker.md), and the `nora_home.tracker` subsystem it
describes is deleted as part of building this.

Todo is **Level 2** (see §1): the base platform depends on it. It is not a house
app and does not live in `houseapps/`.

---

## 1. Levels — the dependency rule this project uses

Recorded here because it is a new architectural decision and Todo is the first
thing to exercise it.

| Level | What | Depends on | Uninstallable |
|---|---|---|---|
| **1** | The base platform, `nora_home/` | — | No |
| **2** | Apps the base leans on. Todo. | Level 1 | Deliberately, and the base degrades |
| **3** | Family apps, `houseapps/` | Levels 1 and 2 | Freely, nothing breaks |

The old rule — *the platform never depends on a house app* — is withdrawn. Levels
replace it. What must not happen is a dependency pointing **downward**: nothing at
Level 1 or 2 may import Level 3.

This needs three things to be real rather than a convention:

- `nora_level` on `NoraAppConfig`, defaulting to 3.
- A level-aware test in `tests/test_house_apps.py`, replacing the current blanket
  "never import another app's models" rule with a directional one.
- `uninstall_app` warning loudly, and naming what breaks, when removing a Level 2
  app the base depends on.

---

## 2. What Todo is

The house's **task** system. Everything that someone needs to do, by some time —
whether the someone is a family member or the house itself, and whether it
originated from a person or from Nora Home.

It is also the house's **calendar**: birthdays, appointments, exams and other
events that consume time without being work you tick off.

### The boundary — what does *not* belong here

| Shape | Goes to | Why |
|---|---|---|
| A number over time (CPU temp, weight, humidity) | **Telemetry** | Nothing to do, nothing to escalate |
| A record that something happened (login, setting changed) | **Audit log** | Same |
| A task | **Todo** | Someone must do something, by some time |

The seam between them is **one-directional**: a telemetry threshold breach or a
repeatedly-failing integration *creates a system task*. The measurement stays in
telemetry where it can be charted; only the "someone should look at this" part
becomes a card. This keeps the system board short and actionable instead of
becoming a log people learn to ignore.

---

## 3. Data model

### Task

The thing, and its rule. One row, one card on the board.

| Field | Notes |
|---|---|
| `title` | Required |
| `description` | Plain text. Not markdown, not rich text |
| `priority` | 1, 2 or 3. **Required at creation, no default.** This *is* the column |
| `labels` | M2M. Several per task |
| `owner` | Who is **responsible**. One person. Escalation chases them (§4a) |
| `assignees` | M2M. Who **can do it**. Any one of them closes it (§4a) |
| `approver` | Optional. When set, completion needs their yes. **Non-recurring tasks only** (§4a) |
| `source` | `user` or `system`. Decides which board it appears on |
| `due_on` / `due_time` | Date, with optional time |
| `deadline_firm` | Bool, default False. **Load-bearing** — see §11 |
| `planned_minutes` | Optional estimate |
| `recurrence_type` | `none` \| `fixed` \| `rolling` |
| `recurrence_spec` | The rule. Meaning differs by type — see §5 |
| `state` | `open` \| `archived` \| `done` |
| `escalation_enabled` | Bool, default **False** |
| `escalation_policy` | FK, when enabled |
| `alarm_kind` / `alarm_ref` | `chime` \| `file` \| `speech`, and its reference |

### Instance

One dated occasion of a task. A one-shot task has exactly one; a recurring task
accumulates one per occasion, forever. **The history is made of instances** —
every statistic in §10 counts them.

| Field | Notes |
|---|---|
| `task` | FK |
| `due_at` | The moment this one was for |
| `outcome` | `pending` \| `awaiting_approval` \| `done` \| `missed` \| `skipped` |
| `completed_at` / `completed_by` | Retroactively editable (§4) |
| `approved_at` / `approved_by` | Set when an approver says yes (§4a) |
| `actual_minutes` | What it really took |
| `note` | "Only managed 20 minutes" |
| `skipped_at` | Only valid **before** `due_at` — see §5 |

**Effective duration** = `actual_minutes` if set, otherwise `planned_minutes`.
That fallback is what lets the load calculation work before anyone has recorded
real times.

### Event

Consumes time; is not work. Birthdays, appointments, exams.

`title` · `description` · `starts_at` · `all_day` · `duration_minutes` ·
`recurrence` (none or yearly) · `labels` · `owner` (or the house) · attachments ·
reminders.

Events appear on the Calendar and **never** on the priority board. They have no
priority, no completion, no escalation.

### Label

**House-wide** (confirmed 2026-08-05), user-created: `name`, `colour`. A task
carries several. There is no second container concept — no projects, no folders.
The sidebar lists every label with a live count.

Shared across the household rather than per-member, so two people can both file
under *Health* and the Everyone view stays coherent.

### Comment · Attachment · Link

All attach to **either a task or an instance** (§4).

- **Comment** — author, body, timestamp.
- **Attachment** — photo, in MinIO.
- **Link** — external URL, *or* an internal path into the house. Internal links
  resolve and display the real name of what they point at, not a raw path.

### Reminder

Belongs to a task or an event; fires for **every** instance of it.

`offset_minutes` (relative — the normal case) *or* `absolute_at` (allowed on
non-recurring tasks only) · `channels` (any of `slack`, `sound`, `inapp`,
`display`).

### ChangeEvent

**The most important table for the future, and the cheapest to get wrong.**

Every reschedule, priority change, label change, skip and archive is its own
dated row: what changed, from what, to what, when, by whom.

Never store `times_moved: 11`. A counter throws away when each move happened and
what surrounded it — information that cannot be reconstructed later and that every
pattern in §10 and §11 depends on. See §13.

### TodoPreference

Per-member settings, owned by this subsystem. Todo renders its own settings page
at `/todo/settings/`; the platform Settings page stays for base-app concerns only.

---

## 4. Rules that hold everywhere

**Three states, and archived is not done.**

- **Open** — sitting in a priority column.
- **Archived** — *"not now, I'll come back to it."* A real column. Archived tasks
  go completely quiet: no reminders, no escalation, no nudges. That is the point
  of parking something. A task keeps its priority while archived, so restoring it
  puts it back where it was.
- **Done** — finished, leaves the board, lives in history.

Completed tasks are reachable through a filter on the Tasks board, the Calendar,
and Reporting. They do not get their own sidebar entry.

**No dragging.** Priority is set at creation and changed by editing the task.
The card renders in that column. Archiving is a button. This was decided
deliberately — no drag library, no touch-drag work, less code.

**Anyone can create a task for anyone.** No approval, no declining. If someone
doesn't want it, they delete it.

**Everything is retroactively editable, and edits flow downstream.** Mark last
Monday done on Wednesday without disturbing Wednesday's own instance. See §13 for
the constraint this places on every statistic in the system.

**Photos and comments attach at both levels.** Task-level for standing context
("use the treadmill when it rains"); instance-level for evidence of one occasion.

---

## 4a. Shared tasks, and approval

Agreed 2026-08-05. Two independent capabilities that happen to arrive together.

### Several people can be on one task

`owner` is who is **responsible**; `assignees` is who **can do it**. The two are
separate on purpose: escalation still has exactly one person to chase, which is
what keeps the ladder meaningful, while the work itself can belong to several.

**Any assignee closes it.** There is no "everyone must tick it" — the first
person to finish it finishes it, and the instance records which of them did
(`completed_by`).

**It appears on every assignee's board**, and the owner's. Scoping filters on
`owner in members OR assignees intersects members`, not on `owner` alone.

**Effort is split, not multiplied.** A 60-minute task shared by three people
contributes **20 minutes to each** of their load calculations. Counting it in
full three times would tell three people they have a full day of work when the
house has one hour of it — and Story 35's scheduling suggestions are built
directly on that number, so the distortion would propagate into advice.

### Approval

**An `approver` being set *is* the approval requirement.** There is no separate
mode flag: no approver means completing is completing; an approver means one
more step. Fewer states to hold, and nothing to keep in sync.

The flow:

```
pending ──complete──▶ awaiting_approval ──approve──▶ done
                             │
                             └──reject (with a reason)──▶ pending
```

**Rejection returns the task to open, and the reason is required.** "No" without
a reason is the thing that makes an approval workflow resented — the person who
did the work is left guessing. The reason is written as a `ChangeEvent`
(`field="approval"`, `to_value="rejected"`, `reason=...`), which means it lands
in the same history every other change does and needs no new table.

**Recurring tasks cannot have an approver.** Deliberate, and enforced at the
model level rather than left as a convention: every occurrence of a daily task
needing someone else's sign-off would be an approval queue nobody keeps up
with, and the first week of it would teach everyone to rubber-stamp. If
something genuinely needs checking every time, that is two tasks — one to do
it, one to check it.

**`awaiting_approval` is not done.** It leaves the board's open columns (the
work is finished) but does not count as a completion in Reporting until
approved, and it does not close a rolling recurrence. Since approvals are
non-recurring only, that last point is theory rather than a case that can
arise — but the rule is stated so it stays true if that ever changes.

### As built (Story 42, 2026-08-05)

`nora_home/todo/api.py` — `complete()` · `approve()` · `reject()` ·
`approval_history()` · `can_complete()` · `doers()` · `tasks_for()` ·
`effort_share_minutes()`. Signatures in
[`cross-functionality.md`](../cross-functionality.md#todo).

Three things the implementation settled that the design above left open:

**`tasks_for()` excludes soft-deleted tasks, and does not exclude archived
ones.** `Task.objects` does no filtering of its own (`SoftDeleteModel` puts
`.alive()` behind an explicit call), so a board that forgot it would show
deleted tasks. Archived stays in, because "not now" is a *column* on the board,
not a deletion.

**`item_completed` fires once, on the transition into `done`** — on
`complete()` for an ordinary task, on `approve()` for one with an approver, and
not at all when someone amends an occasion that was already finished. Firing on
submission would let a receiver congratulate work the approver is about to send
back; firing on an amendment would congratulate the same work twice.

**Rejection keeps `note` and `actual_minutes`, clears `completed_at` and
`completed_by`.** The first pair is the worker's own record and deleting it
because a third party said no is the behaviour this section exists to avoid; the
second is no longer true, and leaving `completed_at` set on a `pending` row is
a lie some later query will trip over.

---

## 5. Recurrence

**Fixed** — "every Monday", "the 1st of each month". Independent of when you last
did it.

**Rolling** — "3 days after I last completed it". The next date is unknowable
until the current one is finished.

### Materialisation

Instances are created **in advance**, within a window:

| Type | Window |
|---|---|
| Fixed | ~90 days ahead |
| Rolling | Exactly one open instance; the next is created on completion |

A nightly job extends the fixed window. `nora_home/tracker/scheduling.py` already
does this correctly and is the code to carry over.

**Rolling recurrences are one deep and cannot be otherwise** — the date does not
exist yet. This is visible on the Calendar: fixed recurrences fill the month,
rolling ones show only their next occasion. Unavoidable, and worth stating in the
UI rather than looking like a bug.

**The board shows one instance per task** — the earliest pending one. Skip a
week of Morning cardio and the board does not grow seven cards; it shows the
current one, and the seven missed instances sit in history where Reporting can
see them.

### Outcomes

A second job closes out instances whose moment has passed with no completion,
marking them `missed`. **This job is the only reason missed days appear in the
charts at all.**

**Skipping has a deadline.** Declared *before* `due_at`: `skipped` — a deliberate
decision, excluded from miss patterns. After the moment passes it is a `missed`,
and it cannot be relabelled a skip retroactively.

---

## 6. Surfaces

### Sidebar

**Search · Tasks · Calendar · Labels · Reporting · System tasks · Settings**

No Inbox. No Today. No Upcoming.

### Tasks

The board: **Priority 1 · Priority 2 · Priority 3 · Archived**, each with a live
count. Filters for label, owner, completed.

Defaults to the logged-in member's tasks, with a toggle widening it to the whole
house. The platform's existing "Everyone" switcher and `scope_members()` provide
this — reuse them rather than building a parallel mechanism.

#### As built (Story 31, 2026-08-05)

`nora_home/todo/views.py`, `forms.py`, `urls.py`; `templates/todo/`. One thing
the design above left implicit, settled by building it: `awaiting_approval`
literally does leave the priority columns (§4a says so), but it still needs
somewhere to be seen and acted on, so it renders in its own strip above the
board instead — visible to whoever can approve or reject it, not sorted into a
priority it has, in the sense that matters, already left.

**A one-shot task's `state` now follows its instance.** Completing, approving,
or skipping the only instance a non-recurring task will ever have moves
`Task.state` to `done` too (§4: "Done — finished, leaves the board, lives in
history"), and `uncomplete()` reverses it. This wasn't specified anywhere
before this story — nothing had ever needed a one-shot task to actually leave
the board — and it only applies to non-recurring tasks; a recurring task's
state never follows its instances, because it has no "last" occasion.

**A platform bug, not a Todo one, found by testing the board in a real browser
rather than trusting the test client.** `NoraHome.post()` (`nh-app.js`) builds
an empty `FormData` for a zero-payload action — a tick, an approve, a skip.
This stack's ASGI request handling rejects a fully empty multipart body
outright with a bare, contentless 400 before Django's view ever runs, which is
also before Django's own error page or logging gets a chance to say anything —
the browser network tab was the only place any evidence of it existed. Every
existing zero-argument call through `NoraHome.post()` had this problem,
including the **tracker's own completion tick**, confirmed broken the same way
with a raw request before the fix and confirmed fixed after. One line: a
FormData with no keys now gets one harmless placeholder field so the body is
never empty. This is why `docs/Main_App/testing.md`'s `./nora qa` exists
separately from the unit suite — the unit suite's Django test client never
builds a real multipart body, so 685 tests stayed green the entire time this
was broken.

### Calendar

Month view only, covering from when the app starts running. Shows:

- Events.
- Task instances — **planned** (materialised, not yet due) and **actual**
  (completed, missed, skipped) in distinguishable visual weights.

Written by hand as a CSS grid. Calendar libraries are large and opinionated about
event rendering, and only one view is wanted.

#### As built (Story 33, 2026-08-05)

`nora_home/todo/calendar.py` (pure date arithmetic — a Monday-starting grid,
year-rolling month shift, yearly-event expansion — tested with no database at
all, same reasoning as `recurrence.py`'s own tests) plus `views.calendar_view`
and `templates/todo/calendar.html`.

**"Actual" is everything except `pending`**, not just `done`. A `missed` or
`skipped` instance is real history too, and hiding it would make the calendar
lie about a week that actually had a gap in it — the same "a gap is honest, a
zero says you failed" reasoning `tracker.api.completion_stats()` already uses
for `rate`. `awaiting_approval` also counts as actual: the work happened, even
though Reporting won't count it as a completion until approved.

**Archived tasks are excluded**, matching reminders and escalation — "not now"
means quiet everywhere, including here. A one-shot task that reached `done`
(Story 31) is **not** excluded: its instance is the record of the day it
actually happened, and removing it because the task itself is finished would
erase real history from view.

**Scoped exactly like the board** — `api.tasks_for(scope_members(request))` —
so a shared task appears on every assignee's calendar and the Everyone toggle
widens it for free, with no separate mechanism.

An out-of-range `?year=`/`?month=` (a hand-edited URL, a stale bookmark after
a leap year) falls back to the current month rather than a 500 — a calendar
that occasionally 500s on a bad link is worse than one that just shows today.

### Labels

Every label, with a live count. Selecting one shows every task carrying it.

**As built (Story 34, 2026-08-05):** `views.labels_view`, `templates/todo/
labels.html`. Counts exclude archived and deleted tasks, matching the
calendar's and reminders' "not now means quiet everywhere" — a label's count
now always matches what selecting it on the board actually shows. The page
also gained a small "New label" form, since nothing before this story let
anyone create one outside `/admin/` — the create/edit form's label picker
only ever offered labels that already existed.

### System tasks

Nora Home's own tasks — the same board, same shape, filtered to `source=system`.
It sits inside Todo, not in the platform sidebar.

#### As built (Story 36, 2026-08-05)

`nora_home/todo/system_tasks.py` is the bridge, and it is one-directional by
construction, not just by convention: it listens to `threshold_crossed`
(already fired by `nora_home.telemetry.api._raise_threshold`) and a new
`integration_failing` signal (fired once per continuous-failure episode from
`nora_home.integrations.tasks._record_failure`, the same point that already
calls `notify_house`) and creates a `Task` from what it hears. Nothing reads a
task back into telemetry or integrations — completing a system task does not
clear a threshold or reset a failure count, which is what keeps the two
subsystems from needing to agree on what "resolved" means.

Wired as signal receivers, not an import of telemetry's or integrations'
models — CLAUDE.md's "never import another app's models" rule, connected in
`TodoConfig.ready()`.

**The dedupe rule is the part that matters.** `_raise_threshold` fires on
*every* off-threshold reading, and `threshold_crossed` with it — a sensor stuck
over its bound for an hour would otherwise put a fresh task on the board every
few minutes. `create_system_task()` checks for an open task with the same
`origin_ref` (`Task.origin_ref`, added this story) before creating a new one,
and reuses it. Once that task is completed or archived, the *next* breach
starts a fresh one — a new occurrence of the problem, not a continuation of the
old one that quietly got un-done.

**Ownership.** `OwnedModel.owner` is required, not nullable, so a system task
needs a real person on it even though the problem belongs to the whole house.
The admin if there is one, otherwise the first active adult; every active adult
is set as an assignee, so `doers()` (§4a) makes it "any adult's to pick up," not
one person's alone. A house with no adult at all returns `None` rather than
raising — a freshly provisioned house must not 500 on its first threshold
breach.

**The board itself is a refactor, not a new page.** `views.board()` and the new
`views.system_board()` both call a shared `_board_context(request, *, source)`
— the priority columns, the awaiting-approval strip, and the label/due-today
filters are one implementation for both boards, exactly as this section says
they should be. `board.html` is one template for both, switched on an
`is_system` flag; the regression this invites — a label-filter link built with
the wrong URL name silently bouncing someone from `/todo/system/` back to
`/todo/` — has its own test.

Verified against the real signals, not just a direct call to
`create_system_task()`: a threshold-crossed and an integration-failing event
each produce a task, a second breach of the same thing reuses it, and the third
consecutive integration failure through the actual `integrations.tasks`
machinery fires the bridge. Then against the Pi's real MySQL, migration
applied and rolled back inside a transaction: the page renders, the dedupe
holds there too, and the house's own data was confirmed untouched before and
after. All five kiosk buttons now exist, and this one was seen on the physical
wall and kiosk — tapped through Todo → System, the demo task showing in its
priority column with no create button, and its default reminder actually
firing a real alert on the wall.

### Reporting

See §10.

### The 24" wall

**The wall is the house's interface to the application, not a summary of it.** It
renders the same board a laptop renders — same columns, same cards, same data.
A chart appears there only because somebody navigated to Reporting on purpose.

The only difference is the **type scale**. The platform already knows which
surface it is rendering to (`nora_home/ui/`), so the wall gets a larger scale
throughout — roughly 1.6× — tuned to read from three metres. Same templates,
same CSS, one variable. Not a separate layout and not separate components.

### The 10.1" kiosk

Two levels, and both are required:

1. **Everywhere** — every destination in the house: the platform's own sections
   and every installed app. The kiosk is the remote for the whole system, not
   for one app.
2. **Inside an app** — whichever app the wall is currently on, showing that app's
   own `nora_kiosk_controls`. Todo's are Tasks, Due today, Calendar, Reporting,
   System tasks, and back to Everywhere.

The kiosk sends `navigate` and the wall follows; the kiosk never navigates itself.

**The limit, unchanged:** a kiosk button cannot post back into an app, so nothing
there can complete a task. That needs a new `app-action` kiosk action at platform
level — deliberately out of scope here, and deserving its own decision since it
would serve every app equally.

**As built (Story 34, 2026-08-05):** both levels already existed, generically,
in `nora_home/displays/views.py: kiosk()` and `templates/displays/kiosk.html`
— built when the kiosk-drives-wall redesign shipped, driven entirely from the
registry, so a new app with `nora_kiosk_controls` gets its own button screen
for free. Todo's own declaration in `apps.py` needed no platform change at
all, confirmed by clicking through it on a real running house: tapping the
Todo tile swaps the kiosk to Todo's own screen, and its buttons work.

**Only three controls today, not five.** Reporting (§10, Story 35) and System
tasks (Story 36) don't have a page to point at yet, and a kiosk tile linking
to a 404 on a wall-mounted touchscreen is worse than a control that simply
isn't there — the same reasoning that keeps `nora_has_page` honest for the
Apps directory. `apps.py` documents adding the other two the moment those
stories ship. "Due today" reuses the board (`/todo/?due=today`) rather than
being a fifth page — one place holds the priority-column and
awaiting-approval logic, not two that could drift apart.

### Widgets

Widgets are for the **home screen** — the personal grid, and whatever the wall
shows when it is pointed at `/home/`. They are not how Todo presents itself; the
app presents itself as the app. Todo ships them to the picker like any other app.

- **`nora_wall_panels` is deleted from the registry.** Already dead code: nothing
  has rendered a wall panel since the wall was repointed at the live app, and the
  only declarers are the tracker and `example_habit`, both being removed. Delete
  the field, the `wall_panels()` function, the contract test and the
  `DEVELOPMENT.md` section.
- **`DashboardLayout.Surface.WALL`** already exists, unused — the same situation
  `SHARED` was in before the Everyone view adopted it. It governs *only* what the
  wall shows when the destination is `/home/`, and it is edited from a phone or
  laptop since the 24" has no input devices. `wall_safe` stays meaningful.

> **Small open item:** what the wall shows at boot, before anyone touches the
> kiosk. Configurable, defaulting to the Todo board.

---

## 7. Search

Full text across titles, descriptions and comments. Combinable filters — label,
priority, owner, state, date range, overdue — and a filter set can be **saved and
returned to**.

### As built (Story 34, 2026-08-05)

`nora_home/todo/search.py` — one function, `search_tasks()`, that both the live
page and a saved filter run through, so a saved search can never mean something
different from the form that produced it. `FilterParams` is the shape of a
filter set — a plain dataclass, built from either a querystring or a
`SavedFilter.params` dict identically.

**Empty on first load**, deliberately — Search is its own destination, not a
second view of "my open tasks"; showing nothing until a query or a filter is
applied is what keeps it from being a redundant mirror of the board.

**"Saved and returned to" needed one new table** — `SavedFilter` (`owner`,
`name`, `params` as JSON), unique per member per name so saving under an
existing name updates it rather than creating a duplicate. Applying a saved
filter is a plain redirect to `?{params}`, the same querystring the form
itself produces — no second interpretation of what a filter means.

Comments are searched at **both** levels a task can carry them (§4: "Photos
and comments attach at both levels") — a task's own standing comments, and
comments on any of its instances — which needs two join paths through the
same `Comment` model, not one.

---

## 8. Reminders

A reminder fires **before or at** the due moment, to help. Escalation fires
**after**, to chase. Different triggers, different tone, both configurable.

- **Relative** offsets everywhere ("30 minutes before", "the evening before at
  8pm"). **Absolute** times allowed on non-recurring tasks only.
- A task given a due date **gets a reminder automatically**.
- **Date-only tasks** fall due at a per-member default hour, 09:00.
- **Fire once.** No snooze, no nagging — escalation is the system designed for
  chasing, and two of them competing is worse than either.

### Routing by priority

| Priority | Reminder | Escalation |
|---|---|---|
| **1** | The person + the family channel | The person + the family channel + each member directly |
| **2** | The person | The person + the family channel + each member directly |
| **3** | The person | The person + the family channel |

### Quiet hours

Both kinds already exist in the base app; use them, do not invent a third.

- **Slack** follows the member's own `quiet_hours_start` / `quiet_hours_end`
  (`HouseMember`, default 22:00–07:00). `notify()` already enforces this.
- **Sound** follows the **house-wide** `notifications.quiet_hours` setting,
  always. Sound comes out of the 24" and everyone in the room hears it, so it is
  not the individual's call.

### Alarms

Per task: a built-in **chime**, an **uploaded audio file** (MinIO), or **spoken
text**.

Speech goes through an external TTS API. **Build to the seam and stop** — a
provider-agnostic interface with one implementation stubbed; the provider is
chosen later.

**Delivery mechanics.** Django runs in Docker; the speakers are the 24"'s, over
HDMI, on the host. This is the same boundary the overnight screen schedule
crossed, and it is solved the same way: a small host-side script run by a systemd
timer, asking the container what is due and playing it. No container privileges,
and broken audio cannot take the house down.

**Backlog after downtime.** If the Pi was off, play only the most recent alarm on
return and collapse the rest into a single "you missed 8 reminders" message.

### As built (Story 38, 2026-08-06)

Three seams, same shape as Story 37's: `nora_home/notifications/tts.py` is the
provider interface plus the one stub this story ships —
`UnconfiguredTTS.synthesize()` raises `TTSError` rather than faking a voice,
which is what lets a speech alarm degrade to silence instead of the reminder
pipeline around it failing because no vendor is chosen yet.
`nora_home/todo/alarms.py` resolves a task's `alarm_kind`/`alarm_ref` to
`(bytes, content_type)` or `None` — chime from a bundled asset
(`static/nora_home/audio/chime.wav`, a two-tone doorbell synthesised with
Python's own `wave` module, not fetched from anywhere), file from object
storage, speech through the TTS seam — and never raises; every failure mode
(missing storage, no provider, an unrecognised chime name) degrades to "no
sound" rather than breaking anything around it.
`nora_home/notifications/channels/sound.py` is the channel, and the one thing
worth knowing about it: **it does not play anything.** It cannot — the
speakers are wired to the Pi's HDMI output, on the host, and Django runs in
Docker with no path to it. `send()` resolves the alarm fresh (from a task id
in the notification's `context`, not precomputed bytes — `context` is a
`JSONField` and audio does not survive a JSON round trip, a bug caught before
it shipped rather than after) and writes it to a bind-mounted cache directory.
A host script on a systemd timer, generated by `scripts/lib/provision-pi.sh`
§10 exactly the way the wall power schedule is, plays the newest file and
does nothing else.

**Gated on the task's `alarm_kind` alone, not on `Reminder.channels`.** The
build brief's own framing suggested routing "sound" through a reminder's
channel list the way Slack/inapp/display already are, but no template
anywhere lets a person put `"sound"` into that list — gating on it would have
made the alarm form field on the task itself (already built, Story 42) do
nothing. `_queue_alarms()` in `reminders.py` triggers on `task.alarm_kind`
being set, for whichever reminder brings the task's occasion due.

**The backlog rule (§10.4) is decided in Django, not on the host.**
`send_due_reminders()` collects every alarm-eligible task due in one sweep; if
more than one, only the most recent gets a real sound and the rest become one
`notify_house()` text summary ("You missed 3 alarms: …"), capped at five
titles named plus a count. The host script's own collapsing (playing only the
single newest file since it last checked) is a second, independent line of
defence for the same rule, not a duplicate of this one — it is what protects
the house even if the Pi being off meant several sweeps' worth of files piled
up in the cache before the host script ran again.

**Quiet hours are house-wide, checked in `alarms.is_quiet_now()`, and
deliberately not `HouseMember.in_quiet_hours()`** — sound comes out of the 24"
for whoever is in the room, so it was never one person's setting to override.

Verified on the real hardware, not just the test suite: a 440Hz tone played
through `plughw:0,0` and was heard clearly from the wall's speakers — the one
fact that could not be established from software alone, since an HDMI audio
*device* existing says nothing about whether a given panel has working
speakers. `hw:0,0` rejects `speaker-test`'s own parameters outright
("Setting of hwparams failed: Invalid argument"); `plughw:0,0` lets ALSA
convert and is what every playback path in this story uses.

### As built (Story 32, 2026-08-05)

`nora_home/todo/reminders.py`. `ensure_default_reminder(task)` fills the "gets
one automatically" rule — called from the create/edit views, never overrides a
reminder someone set up themselves, and never duplicates one. `send_due_reminders()`
is the Celery task (`todo.send-reminders`, every 5 minutes) that actually fires
them, via `notify()`/`notify_house()` — **fire-once is enforced by their existing
`dedupe_key` mechanism**, per a generous 30-day window keyed to the instance's own
uuid, rather than a new "sent" flag on the model. That is what the build brief
pointed at (4.6) rather than inventing a second mechanism.

**Reminders fan out to every assignee, not just the owner** — `api.doers(task)` is
the same function the effort-split calculation uses. Escalation does not; see
below.

~~**Sound is accepted and silently dropped**, not forwarded to `notify()`.~~
**Resolved by Story 38.** A real `SoundChannel` exists now — see "Alarms" §
"As built" above — but it turned out sound is triggered by a task's own
`alarm_kind`, not by `Reminder.channels` at all (no template lets a person add
`"sound"` to that list). `ALARM_CHANNEL` is still filtered out of the
per-recipient `notify()` loop in `_send_reminder()`, now as defensive
filtering against a value nothing sets rather than as the thing doing the
dropping.

Event reminders (`Reminder.event`) are **not evaluated yet**. A recurring event's
next occurrence needs the same calendar arithmetic Story 33 is going to build;
writing a narrower, second version of it here to unblock reminders would just be
something to keep in sync later. `Reminder` accepts an event today; nothing reads
it until Calendar exists.

---

## 9. Escalation

Carried over from the tracker largely intact — it works, it is tested, and it is
the piece that makes this more than a list.

**Opt-in, off by default.** Escalating "Join AI & Robotic Communities" would be
noise. Enabled per task; policies remain editable in the admin.

**Archived tasks never escalate.**

### As built (Story 32, 2026-08-05)

`nora_home/todo/escalation.py` — the tracker's `EscalationPolicy` model, ladder
shape, and audience resolution (`owner` / `chain` / `adults` / `house`) reused
directly, walking `Instance` instead of `Occurrence`. Two deliberate departures
from a literal port:

- **No second `EscalationEvent` table.** Each rung firing is written as a
  `ChangeEvent` (`field="escalation"`) instead — Todo already has one
  append-only history table for everything that happens to a task, and an
  escalation is exactly that kind of event. Same reasoning as reusing
  `ChangeEvent` for the approval trail (§4a).
- **The audience is always the task's `owner` alone, never its `assignees`.**
  A shared task still has exactly one person the ladder chases — the same
  reasoning that keeps escalation meaningful on a shared task at all (§4a):
  fanning out to everyone who *could* do it would turn the chain-of-contacts
  ladder into a group chase with no one actually accountable. Reminders are
  the fan-out mechanism; escalation is the accountability one.

A task with `escalation_enabled=True` but no explicit `escalation_policy` falls
back to `EscalationPolicy.get_default()` — the same "House default" resolution
the tracker's own `register_trackable()` already uses, reused rather than
reinvented.

**Acknowledging** ("seen it, will get to it") is new UI, not new mechanism —
`Instance.acknowledged_at`/`acknowledged_by` existed since Story 30, written by
nothing until now. `api.acknowledge()`, a `todo:acknowledge` view, and a "Seen
it" button on the detail page's current occasion (shown once escalation has
actually reached level 1) are what finally give the ladder a stop button beyond
completing the task outright.

---

## 10. Reporting

Todo has its own visualization page. Its widgets are also offered to the home
screen and the wall through the normal picker.

### Charts

**Designed for this house:**

| Chart | Answers |
|---|---|
| Realistic load | "You typically finish 4–6 things. Today has 43." |
| Deferral patterns | Which labels keep sliding, and by how much |
| Time to first touch | How long between writing it down and acting |
| Priority drift | What share sits in Priority 1 — whether priority still means anything |
| Aging | Oldest open items, with one-tap archive beside each |
| Evidence of agency | A plain list of what you decided to do and then did |
| Recovery after gaps | Stopped for nine days and came back — shown as a positive |

**Standard, and they earn their place:**

| Chart | Answers |
|---|---|
| Cumulative flow | Arriving vs. completing — "is the pile growing?" |
| Cycle time | Created → done, and started → done |
| Throughput histogram | The real distribution, not an average |
| Calendar heatmap | The GitHub-contributions shape. ECharts does this natively |
| Aging work-in-progress | Open items by age, per column |
| Time of day / day of week | When you actually get things done |
| Label distribution | Where attention really goes, versus where you think it does |
| Estimate accuracy | Planned vs. actual, over time |

### Tone

The gentler defaults are **defaults, not rules**. A preset sets everything at
once; individual overrides sit underneath. **Standard** is the default.

| Setting | Calm | Standard | Competitive |
|---|---|---|---|
| Streaks | Rolling ratio ("19 of 30") | Rolling ratio | Classic, resets on a miss |
| Counts in red | Never | Overdue only | Everything |
| Compare household members | Off | Off | Leaderboard |
| Wording | "Moved 11 times" | "Overdue 11 days" | "Overdue 11 days" |
| Pattern observations | Reporting page only | Reporting page only | Also on the home screen |
| Wall / kiosk / widgets show | Next 3 | Next 5 | Everything |

Nothing is withheld from anyone. Someone who wants a streak that resets to zero
can have one.

### Visual discipline

The platform's own home dashboard is the cautionary example, and these are its
actual failures. Todo's Reporting page holds itself to the right-hand column.

| What went wrong there | The rule here |
|---|---|
| A chart drawn with **no data** — "Reliability" renders a full 0/0.2/…/1 axis with nothing plotted | Empty is a **sentence**, never an axis. One line of text, one line of space |
| A **huge box holding one line** — "House vitals" is a quarter of the screen for one temperature | Height follows content. Two rows of content occupy two rows of card |
| **Ragged alignment** — cards at different vertical offsets, arbitrary gaps | One grid, aligned rows, a single gap value. Nothing floats |
| **Ratio axes** — 0 to 1 in steps of 0.2, which nobody reads as a percentage | Percentages are percentages, durations are durations. Axis labels use the unit a person would say aloud |
| **Chart furniture** — threshold lines, arrow markers, dotted rules adding marks but no information | Every mark earns its place |
| **Large cards for absence** — "Nothing late. Good." twice, at full tile size | Good news is small. The quiet state is the compact state |

Two more throughout: numbers in columns use `tabular-nums` so they do not jitter
on refresh, and the accent is spent on one thing per screen — everything else
stays in the neutral ink range.

### As built (Story 35, 2026-08-05)

`nora_home/todo/analytics.py` holds one documented function per metric, all
computed from history on read, and it is the only place in this app a statistic
is derived — `overview()` is a convenience over those same functions, not a
seventeenth one. `tone.py` decides *presentation* and never touches a number,
which is what lets someone switch preset and see the other streak shape with no
recomputation and no stored state.

**The flagged risk was real, and it was in the arithmetic.** `priority_distribution()`
counted **one task per priority**. `Task.Meta.ordering` is `["priority", "-created_at"]`,
and Django appends the ordering fields to the `GROUP BY` of a
`values().annotate()` — so the query grouped by `(priority, created_at)`, one
row per task, and the dict comprehension reading it back kept only the last row
per priority. Every count came out as `1`, percentages with them. The table
rendered perfectly; it was simply full of wrong numbers, which is exactly the
failure mode this story was flagged for. `.order_by()` before `.values()` clears
the inherited ordering. It was caught only because the test used three tasks in
one priority — a single task per priority passes either way.

Two smaller ones: `reporting.html` styled its cards with `.pane`, which does not
exist in this codebase (the house's glass class is `.card`), so five cards
rendered with no card at all; and `today.replace(year=today.year - 1)` raises
`ValueError` on 29 February, in both the heatmap chart and the heatmap widget —
the Reporting page and the home screen would each have 500'd one day every four
years.

**The Visual discipline table needed a second pass, after looking at the wall.**
The first version rendered an empty house as twelve near-full-size cards each
saying "Nothing finished yet." — breaking two of its own six rules, "large cards
for absence" and "a huge box holding one line", on the page written to avoid
them. Reading the template would not have caught it; the rule only fails when
you see the whole screen at once. An empty card now drops its subtitle (it
explains how to read a chart that is not there) and collapses to a single
baseline-aligned row. Two tests hold the rule, one in each direction.

`_chart_card.html` is where "empty is a sentence, never an axis" is decided, so
it is one decision in one place rather than eight. `views._reporting_charts()`
returns `None` for anything with nothing to draw and the partial renders that as
text; no chart option is ever built with an empty series. Chart options carry no
colours — `NoraHomeCharts.render()` merges the house theme underneath, which is
what keeps Reporting looking like the same system as every other chart in the
house.

Reporting also joined `nora_kiosk_controls` now that it has a page to point at,
so four of the design doc's five kiosk buttons exist; System tasks (Story 36) is
the one still missing.

---

## 11. Scheduling recommendations

When a large task or event lands, propose what to move — as one-click suggestions,
not a rearranging exercise.

**Capacity is learned, not guessed.** From throughput history: how many hours of
planned work this person actually completes, by day of week. Saturdays are not
Tuesdays.

**The calculation** — for each day: `capacity − events − tasks due = headroom`.

**When headroom goes negative**, produce concrete moves — *"Thursday is 4 hours
over. Move these three to Saturday, which has 3 hours free. Drop this one, you
have deferred it nine times."* One click applies the lot.

**`deadline_firm` is what makes this possible.** "File taxes by the 15th" cannot
move; "Research flow state" can move indefinitely. Without the flag every
suggestion is guesswork. One checkbox, defaulting to flexible.

**It runs only when a day actually goes over.** A scheduler that comments on every
task added becomes noise within a week.

### Arithmetic, not AI

The core is a greedy scheduler over durations, priorities and slack —
deterministic, instant, free, works with the internet down, and **explainable**.
*"Moved because Thursday was 4 hours over and this is flexible with 11 days of
slack"* is a sentence a person can check. An LLM's rearrangement is one they have
to trust, and this reshuffles their week.

AI's place is the **judgement layer above** it — noticing that an exam needs
preparation time nobody scheduled, or that everything labelled *Health* has
quietly been dropped for three weeks. That is pattern-reading. It is optional,
clearly marked as opinion rather than calculation, and it is **not built now**.

---

## 12. Slack

### Socket Mode, and why

Slash commands and interactive buttons require Slack to **reach the server**. The
Pi is behind home NAT with a self-signed certificate; Slack cannot call it and no
scope changes that.

**Socket Mode** has the app open an outbound websocket *to* Slack. No public
endpoint, no port forwarding, no tunnel, no domain. It is Slack's supported path
for exactly this situation.

Cost: a persistent process holding the socket — a small fourth container beside
`web`, `worker` and `beat`.

Considered and rejected: a Cloudflare Tunnel (also outbound, gives a public HTTPS
URL for ordinary webhooks) — a genuine alternative, rejected to avoid depending on
a third party and adding another moving piece to provisioning.

*Confirm Slack's current concurrent-connection limits against their docs at build
time rather than trusting this document.* **Checked 2026-08-06: 10 concurrent
websocket connections per app, and payloads may arrive on any of them.** This
house opens exactly one, from a single container, so the limit is nowhere near
binding — but it is the reason the socket must never be run from the worker,
which would open one per process and could hand the same interaction to a
different one than sent it.

### What it enables

- **One slash command, `/todo`, with subcommands** — `/todo ack 123`,
  `/todo approve 5 looks good`, `/todo new Buy milk`, `/todo help`. Decided
  2026-08-06 over three separate commands (`/todo-ack`, `/todo-approve`,
  `/todo-new`): Slack only needs one command registered, every action routes
  through one Socket Mode handler, and a future action is a new case in that
  handler, not a new command to register in the Slack app config. The cost is
  Slack's per-command autocomplete hint — typing `/todo-ack` used to show its
  own description; `/todo` shows one generic one, and `/todo help` is the
  fallback for discoverability. Worth it for a house of four people.
- **Buttons on the message itself** — Done · Skip · Snooze · Reassign. Same
  plumbing, and better than typing a slash command on a phone.

### Permissions to assign

Bot token scopes:

| Scope | For | Status |
|---|---|---|
| `chat:write` | Posting messages | Already granted |
| `commands` | Slash commands | Already granted |
| `chat:write.public` | Posting to channels the bot has not joined | **Needed** |
| `im:write` | Opening and sending DMs | **Needed** |
| `users:read` | Mapping house members to Slack accounts | **Needed** |
| `reactions:write` | Acknowledging with an emoji | **Needed** |

App-level token (separate, starts `xapp-`): **`connections:write`** — Socket Mode.

Also: enable **Socket Mode**, enable **Interactivity**, create the single `/todo`
slash command, and record each member's `slack_user_id` (the existing
`slack_members` command does the matching — `nitin` and `priya` were set
directly, 2026-08-06, ahead of that command existing).

**Until these are granted, nothing reaches Slack.** Build against it, but verify
early. *(All granted 2026-08-06, and each scope verified against the live API
rather than taken on trust — `users:read` by resolving both members' real
Slack IDs back to their names.)*

### As built (Story 37, 2026-08-06)

Three pieces, split along the Levels boundary (§1) rather than by convenience:

**`nora_home/notifications/slack_socket.py`** holds the websocket and nothing
else. Two things in it are load-bearing and both are easy to get wrong. It
**acknowledges the envelope before doing any work** — Slack retries an
unacknowledged one, so a slow handler does not produce a late reply, it
produces the same task completed twice. And it calls `close_old_connections()`
around every dispatch, because slack_sdk runs listeners in its own thread pool
and Django's connections are thread-local: without it those threads accumulate
connections MySQL has long since dropped, and the first symptom is an
interaction failing hours after the process looked healthy. Everything the
house actually *decides* is in `reply_for()`, a pure function over a dict, so
it is testable with no network, no token, and no slack_sdk installed.

**`nora_home/notifications/slack_commands.py`** is a registry — `@command` and
`@action` — that knows how to resolve a Slack user id to a `HouseMember` and
nothing about what any command means. **Matching is on `slack_user_id` alone,
never on name or email**: a Slack display name is not an identity, and acting
on a guess would mean completing somebody else's task. `TodoConfig.ready()`
registers `/todo` into it, the same way `IntegrationsConfig.ready()` registers
providers, so the base platform never imports the app by name.

**`nora_home/todo/slack_commands.py`** is what `/todo` means. Every action goes
through `nora_home.todo.api` — not the models, not the views — so Slack gets
the same permission checks, approval transitions and change trail the board
does, and cannot become a back door around them. When the api raises, the
person sees the api's own wording, because those messages are already written
for a human and two vocabularies for one rule is worse than one.

Buttons reach the message through **`slack_actions` in the notification's
context**, a generic list of `{action_id, text, value}` the Slack channel
renders. The channel stays Level 1 and never learns what a task is; an app
supplies data and the platform renders it, the same seam the widget registry
uses.

**The Skip button is conditional, and finding out why was the useful part.**
§5 draws the line at the due moment: declining beforehand is a deliberate
decision excluded from miss patterns, and `api.skip` refuses afterwards
because by then the occasion is a miss. But the default reminder fires *at*
`due_at`. So a Skip button would have been present, and permanently broken, on
almost every reminder the house sends — caught by a failing test rather than
by reasoning, and fixed by offering it only while it can still work. That is
the same rule §10 applies to empty charts: do not draw a control that cannot
act. Snooze exists for the case Skip no longer covers, and deliberately creates
a new `Reminder` rather than moving `due_on` — "remind me after dinner" is not
the claim "this is due tomorrow", and moving the date would write a deferral
into the trail `analytics.deferral_by_label()` reads.

The container exits 0 when Slack is unconfigured, and is the only service with
`restart: on-failure` rather than `unless-stopped` — a house with no Slack app
is a supported configuration, and should not have a process restart-looping
against a missing token.

---

## 13. Built so AI can be added later without a refactor

The expensive mistake is not the code — it is **data thrown away**. Four rules:

1. **Record changes as dated events, never counters.** `times_moved: 11` loses
   when each move happened, from what to what, and what else was going on.
   Unreconstructable later. See `ChangeEvent` in §3.
2. **Instances are first-class rows**, so intent and outcome are both preserved.
3. **All statistics live in one read module**, `nora_home.todo.analytics`, one
   documented function per metric. Charts call it, MCP tools call it, and a future
   AI layer calls the same functions rather than re-deriving anything.
4. **MCP tools from day one.** Once analytics exists, exposing it is nearly free,
   and it lets an agent read the house's patterns before any bespoke AI feature
   is written.

### No stored counters — the hard constraint

Because history is retroactively editable, **every statistic is computed from
history on read.** A cached "19 of 30" silently goes wrong the moment someone
corrects a day three weeks back, and nobody would ever know. Anything cached for
speed must be invalidated when history changes.

This is written down because the tempting optimisation is exactly the thing that
breaks it.

---

## 14. What is deleted

- **`nora_home/tracker/`** entirely — models, API, widgets, cards, MCP tools,
  admin, urls, views.
- **`nora_home.tracker.api`** as a published surface. It becomes
  `nora_home.todo.api`. Nothing but `example_habit` calls it, and that is being
  deleted, so this is a clean cut with no compatibility shim.
- **`nora_wall_panels`** from the registry, its `wall_panels()` function, the
  contract test, and its section in `DEVELOPMENT.md` — dead since the wall was
  repointed.
- **`bootstrap_home`'s** tracker seed data, and the three seeded escalation
  policies get a new home under Todo.
- **`docs/Main_App/subsystems/tracker.md`**, replaced by this file.

Carried over rather than rewritten: `scheduling.py` (materialisation) and
`escalation.py` (the ladder). Both work and are tested.

---

## 15. Platform work this depends on

Not part of Todo, but Todo needs or triggers each of them.

| # | Work |
|---|---|
| 1 | **House log page** — audit, health, deliveries, integrations, telemetry events on one timeline with filters and charts, under House in the sidebar |
| 2 | **Audit coverage** — `record()` currently has four call sites, three of which are being deleted. The page is empty without this; they ship together |
| 3 | **Levels** — `nora_level`, level-aware dependency test, `uninstall_app` warning |
| 4 | **Alarm audio** — host script + systemd timer, HDMI to the 24", TTS seam |
| 5 | **Telemetry → system task bridge** — a threshold breach creates a card |
| 6 | **Slack Socket Mode container** + the scopes in §12 |
| 7 | **Wall as a widget surface** — adopt `Surface.WALL`, plus a remote editor |
| 8 | **Delete `nora_wall_panels`** |
| 9 | **Delete `houseapps/example_habit`** — already agreed |

---

## 16. Open, and deliberately deferred

- **TTS provider** — built to the seam, provider chosen later.
- **AI judgement layer** (§11) — designed for, not built.
- **Snooze** — deliberately absent; revisit if reminders are being missed.

---

## 17. What "done" means

1. Unit tests for Todo's own logic, the platform suite green.
2. `./nora qa` green, with browser tests for the board, calendar and reporting.
3. Deployed to the Pi and **observed** — board renders, reminders arrive in
   Slack, an alarm actually plays through the 24"'s speakers, the wall shows the
   chosen widgets.

Until every one of those is seen with someone's own eyes it is **built, unproven**
— never Complete.
