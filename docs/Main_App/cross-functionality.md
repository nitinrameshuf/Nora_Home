# cross-functionality.md — what each app offers every other app

**The point of this file.** Nora Home is a platform. An app should almost never
build scheduling, reminders, escalation, notifications, charts, storage, or AI for
itself — the platform already has all of it, and using the shared version is what
makes a new app feel like part of the house instead of a website that happens to be
hosted next to one.

This is the index of everything one app may call from another. If you want a
capability and it is listed here, call it. If it is not listed here, it is not a
public surface — see [§ The rule](#the-rule) at the bottom.

**The tables below are generated.** `manage.py sync_docs` rewrites everything
between the `sync_docs` markers straight from the code, and
`tests/test_docs_in_sync.py` fails the suite when a committed block no longer
matches. Do not hand-edit inside the markers — the prose around them is yours.

<!-- sync_docs:begin installed-apps -->

| App | Level | URL | Nav | Sections | Widgets | Kiosk keys | MCP |
|---|---|---|---|---|---|---|---|
| **Displays** <br><code>nora_home.displays</code> | 1 | `/home/displays/` | — | — | — | — | — |
| **Alerts** <br><code>nora_home.notifications</code> | 1 | `/home/alerts/` | yes | — | — | — | — |
| **Assistant** <br><code>nora_home.ai</code> | 1 | `/home/ai/` | — | — | — | — | — |
| **Measurements** <br><code>nora_home.telemetry</code> | 1 | `/home/measurements/` | yes | — | 1 | — | yes |
| **Integrations** <br><code>nora_home.integrations</code> | 1 | `/home/integrations/` | yes | — | — | — | — |
| **Home** <br><code>nora_home.core</code> | 1 | `/home/` | — | — | 3 | — | — |
| **Interface** <br><code>nora_home.ui</code> | 1 | `/ui/` | — | — | — | — | — |
| **Dashboard** <br><code>nora_home.dashboard</code> | 1 | `/dashboard/` | — | — | — | — | — |
| **Todo** <br><code>nora_home.todo</code> | 2 | `/todo/` | yes | 7 | 6 | 5 | yes |
| **Household** <br><code>nora_home.accounts</code> | 1 | `/accounts/household/` | — | — | — | — | — |
| **MCP** <br><code>nora_home.mcpserver</code> | 1 | `/mcp/` | — | — | — | — | — |
| **Data** <br><code>nora_home.datastores</code> | 1 | `/data/` | — | — | — | — | — |

<!-- sync_docs:end installed-apps -->

### Everything one app may call from another

<!-- sync_docs:begin published-api -->

### `nora_home.todo.api`


| Call | What it does |
|---|---|
| `acknowledge(instance, *, member) -> 'Instance'` | Stop the escalation ladder without claiming the work is done — "seen it, will get to it" (§9, ported from the tracker's own `Occurrence. acknowledge()`). Anyone the escalation reached can silence it: the owner, or anyone on their escalation chain who just got pulled in by a widening rung, not only the person who happened to be first notified |
| `approval_history(instance)` | Every submit/approve/reject on this occasion, newest first — which is what makes a rejection's reason retrievable at the point it matters |
| `approve(instance, *, member, at=None) -> 'Instance'` | The approver says yes. Only then is it done |
| `can_complete(task, member) -> 'bool'` | Any assignee closes it — the first person to finish it finishes it. The owner can always close their own task, whoever else it is shared with |
| `complete(instance, *, member, actual_minutes=None, note=None, at=None) -> 'Instance'` | Finish one occasion |
| `doers(task) -> 'list'` | The people who actually do this task |
| `effort_share_minutes(instance, member=None) -> 'float | None'` | How many minutes this occasion adds to **one person's** load |
| `record_changes(task, before: 'dict', *, actor=None) -> 'int'` | Write one dated `ChangeEvent` per field that actually moved. Returns how many were written; zero when someone opened the edit form and saved it unchanged, which should leave no trace at all |
| `reject(instance, *, member, reason: 'str') -> 'Instance'` | The approver says no, and says why |
| `skip(instance, *, member, reason: 'str' = '', at=None) -> 'Instance'` | Mark an occasion skipped — deliberately not done, before its moment passed. Once `due_at` has gone, the occasion is a miss instead (§5); the board and `close_passed_instances` are what turn a lapsed pending instance into `missed`, not this function |
| `snapshot(task) -> 'dict'` | What `record_changes()` compares against. Take one *before* saving an edit, pass it back afterwards |
| `tasks_for(members, *, queryset=None)` | Tasks belonging to these people: `owner in members OR assignees intersects members` |
| `uncomplete(instance, *, member) -> 'Instance'` | Undo a tick. Back to `pending`, whether it was `done` or still `awaiting_approval` — the person who finished it (or the approver who signed off) is allowed to say "actually, not yet" |


### `nora_home.notifications.api`


| Call | What it does |
|---|---|
| `notify(recipient, *, title: 'str', body: 'str' = '', app_slug: 'str' = '', severity: 'str' = Severity.INFO, url: 'str' = '', icon: 'str' = '', channels: 'list[str] | None' = None, dedupe_key: 'str' = '', dedupe_minutes: 'int' = 60, sync: 'bool' = False, **context) -> 'Notification | None'` | Tell one person something. Returns None if deduplicated away |
| `notify_house(*, title: 'str', body: 'str' = '', app_slug: 'str' = '', severity: 'str' = Severity.INFO, url: 'str' = '', icon: 'str' = '', channels: 'list[str] | None' = None, dedupe_key: 'str' = '', dedupe_minutes: 'int' = 60, sync: 'bool' = False, **context) -> 'Notification | None'` | Tell everyone. Goes to the house Slack channel and the wall display |


### `nora_home.telemetry.api`


| Call | What it does |
|---|---|
| `define_series(key: 'str', label: 'str', *, unit: 'str' = '', app_slug: 'str' = 'telemetry', category: 'str' = '', member=None, direction: 'str' = 'neutral', description: 'str' = '', warn_below=None, warn_above=None, alert_below=None, alert_above=None, show_on_wall: 'bool' = False, precision: 'int' = 2, retention_days: 'int' = 730) -> 'Series'` | — |
| `record_reading(key: 'str', value: 'float', *, member=None, source: 'str' = 'manual', recorded_at=None, app_slug: 'str' = 'telemetry', **tags) -> 'Reading'` | Store one measurement and fire a threshold signal if it crosses a bound |
| `series_history(key: 'str', *, hours: 'int' = 24, limit: 'int' = 500)` | — |


### `nora_home.core.api`


_Publishes nothing._

<!-- sync_docs:end published-api -->

---

## At a glance

| You want to… | Call | Lives in |
|---|---|---|
| Make something show up as due / overdue / escalating | *no app-facing call yet* — see [Tracker — removed](#tracker--removed) | [Todo](#todo) |
| Finish, approve or reject one occasion of a todo | `todo.api.complete()` / `approve()` / `reject()` | [Todo](#todo) |
| Find the tasks that belong to some people | `todo.api.tasks_for()` | [Todo](#todo) |
| Tell one person something | `notifications.api.notify()` | [Notifications](#notifications) |
| Tell the whole house something | `notifications.api.notify_house()` | [Notifications](#notifications) |
| Record a number over time, get charts + thresholds free | `telemetry.api.record_reading()` | [Telemetry](#telemetry) |
| Put a tile on the home dashboard | subclass a `dashboard.widgets` class | [Dashboard](#dashboard-widgets) |
| Put something on the 24" wall | `displays.bus.send_to_display()` | [Displays](#displays) |
| Ask Claude something | `ai.client.ask()` | [AI](#ai) |
| Store a document whose shape will change | `datastores.mongo.put_document()` | [Datastores](#datastores) |
| Store a file / photo / export | `datastores.objects.put_bytes()` | [Datastores](#datastores) |
| Expose your data to AI agents | `@mcpserver.registry.mcp_tool` | [MCP](#mcp) |
| React to something another app did | `core.signals` | [Signals](#signals) |
| Filter a widget to the right people | `core.registry.scope_members()` | [Dashboard](#dashboard-widgets) |

---

## Tracker — removed

`nora_home.tracker` was **deleted on 2026-08-06 (Story 40)**. Todo does its job;
see [Todo](#todo) below and
[`subsystems/todo.md`](subsystems/todo.md).

Most of what the tracker published has a direct successor — `EscalationPolicy` is
now `nora_home.todo.models.EscalationPolicy`, with the same three seeded ladders
(*House default*, *Gentle*, *Safety critical*), still editable in `/admin/`
without a deploy. The MCP tools it published, `open_items` and
`member_reliability`, kept their names and now answer from Todo.

> **One thing has no successor yet, and you need to know before you plan an app.**
> The tracker published `register_trackable()` — the call that let a house app
> hand the platform a recurring job keyed on `(app_slug, source_ref)` and get
> due dates, reminders, streaks and escalation for free. **Todo has no
> equivalent.** Its API is written for a person operating a board, not for
> another app registering work: there is a `Task.origin_ref` field, but the only
> thing that writes it is `nora_home.todo.system_tasks`, which is internal.
>
> What the app-facing version should look like on Todo's model is a design
> question rather than a mechanical port, so it is deliberately left to **Story
> 24** — the first real family app, which is the first thing that will actually
> need it. Until that is settled, an app that needs recurrence either drives
> `nora_home.todo.api` directly or keeps its own schedule. Do not invent a
> `register_task()` here without agreeing its shape first; a half-designed
> registration API is worse than none, because apps will build on it.

---

## Todo

`from nora_home.todo import api as todo`

Todo is **Level 2** — an app the base platform deliberately leans on, and the one
that replaces the Tracker (see
[`subsystems/todo.md`](subsystems/todo.md) §1). Only the pieces that exist today
are listed; the rest arrives with the phases that build it.

What is here now is **one occasion's journey through its outcomes**, and the two
things sharing a task with other people changes for everyone else:

```
pending --complete--> awaiting_approval --approve--> done
                              |
                              +--reject (reason required)--> pending
```

With no approver, `complete` goes straight to `done` — the same call either way,
so a caller never has to ask which kind of task it is holding.

| Function | Does |
|---|---|
| `complete(instance, *, member, actual_minutes=None, note=None, at=None)` | Finish one occasion. Lands on `done`, or `awaiting_approval` when the task has an approver. `at` is for retroactive corrections — ticking last Monday must not disturb today |
| `approve(instance, *, member)` | The approver says yes; only now is it `done`. `PermissionDenied` for anyone else |
| `reject(instance, *, member, reason)` | Back to `pending`. **The reason is required** and is stored as a `ChangeEvent`, not a new table |
| `approval_history(instance)` | Every submit / approve / reject on that occasion — how a rejection's reason is retrieved |
| `can_complete(task, member) -> bool` | Owner or any assignee. Any one of them closes it; there is no "everyone must tick it" |
| `doers(task) -> list` | Who actually does it — the assignees, or the owner alone when it is unshared |
| `tasks_for(members, *, queryset=None)` | Scope to people: `owner in members OR assignees intersects members`. Carries the `.distinct()` this needs, and excludes soft-deleted tasks (archived ones stay — "not now" is a column, not a deletion) |
| `effort_share_minutes(instance, member=None) -> float \| None` | Minutes this occasion adds to **one** person's load. `None` when nobody estimated it, which is different from `0.0` |
| `skip(instance, *, member, reason="", at=None)` | Deliberately not done, before the moment passes. Refused once `due_at` has gone — after that it's a miss (§5), not something still skippable |
| `uncomplete(instance, *, member)` | Undo a tick, from `done` or `awaiting_approval` back to `pending`. Allowed for whoever could complete it, or the approver |
| `acknowledge(instance, *, member)` | "Seen it, will get to it" — stops the escalation ladder without completing the task |

A one-shot task whose only instance resolves — via `complete()`, `approve()`, or
`skip()` — has its `Task.state` moved to `done` too, so it leaves the board
entirely rather than sitting in a priority column with nothing left to show.
`uncomplete()` reverses that. A recurring task's state never follows its
instances; it has no "last" occasion to be finished by.

**Two traps this API exists to stop you hitting.**

Filtering a board on `owner` alone hides tasks from the people they were shared
with — always go through `tasks_for()`. And **effort splits, it never
multiplies**: a 60-minute task shared by three is 20 minutes each, because
counting it in full three times tells three people they have a full day of what
is one hour of house work, and the scheduling suggestions are built on that
number.

**Recurring tasks cannot have an approver.** Enforced in `Task.clean()` *and* as
a database `CheckConstraint`, so a management command or a data import cannot
quietly create one.

**Two more modules, not re-exported through `api.py`** because they act on
their own schedule rather than in response to a request:

- `nora_home.todo.reminders` — `ensure_default_reminder(task)` and
  `send_due_reminders()`. Fans reminders out to every assignee via `doers()`.
- `nora_home.todo.escalation` — `escalate_due_instances()`, ported from the
  deleted tracker's engine onto `Instance`. Chases the owner alone, never the
  assignees — see `todo.md` §9.

---

## Notifications

`from nora_home.notifications import api as notifications`

Channel-agnostic delivery with dedupe, quiet hours, delivery receipts, and retries.
You never pick a transport; the recipient's preferences and the severity do.

```python
notifications.notify(
    member,
    title="Water filter is due",
    body="Kitchen, every 90 days.",
    app_slug="maintenance",
    severity="warning",            # info|nudge|warning|alert|critical
    url="/maintenance/filters/3/",
    dedupe_key="filter-kitchen-due",   # suppresses repeats in the dedupe window
) -> Notification | None      # None when deduplicated away

notifications.notify_house(title=..., body=..., severity="alert", app_slug=...)
```

| Severity | Meaning |
|---|---|
| `info` | Background fact |
| `nudge` | Gentle, ignorable |
| `warning` | Should be dealt with |
| `alert` | Ignores quiet hours |
| `critical` | Ignores quiet hours; holds the wall until replaced |

**Channels:** `slack`, `inapp`, `display` (the 24" wall), `console`, `sound`.
Pass `channels=[...]` only to force one — normally let the platform resolve it.

### Speech — making the house say something out loud

`from nora_home.notifications.speech import speak`

```python
speak("The bins go out tonight.")                      # -> bool

speak("The smoke alarm is going off.",
      app_slug="safety",
      respect_quiet_hours=False,   # only for things that genuinely outrank it
      sync=True)                   # skip the worker; for a shell or a test
```

Returns whether a sound was **queued** — `False` covers no text, no TTS provider
configured, and quiet hours alike, because the caller only needs to know whether
the house is about to speak. **It never raises**: asking for a voice at 3am, or
before anyone has set an API key, must not be able to break the app that asked.

**Call this rather than `nora_home.notifications.tts` directly.** Three things sit
between text and a noise in the kitchen and only one is synthesis: quiet hours are
house-wide (sound comes out of the 24" for whoever is in the room), and the audio
has to reach the *host*, because the speakers are wired to the Pi's HDMI and Django
runs in a container with no path to them. An app calling the provider itself would
get correct audio, inside a container, at 3am, that nobody would ever hear.

Todo's `alarm_kind="speech"` uses the same provider through
`nora_home.todo.alarms`; there is no second implementation.

> **No queueing or mixing.** The house has one pair of speakers and one file is
> written at a time, so two `speak()` calls a second apart are two sounds a second
> apart. Collapsing a burst is the caller's job, because only the caller knows
> whether its eight things are eight announcements or one — see Todo §10.4, which
> turns a backlog of alarms into a single "you missed 8 reminders".

**Configured in `.env`**, not the database (CLAUDE.md §4): `NORA_HOME_TTS_PROVIDER`
(`none` | `groq`), `NORA_HOME_GROQ_API_KEY`, `NORA_HOME_TTS_VOICE`. With no
provider the house still boots and still runs reminders — only spoken alarms go
quiet.

---

## Telemetry

`from nora_home.telemetry import api as telemetry`

One time-series store for every number in the house. Record here instead of adding a
`weight` column and you get charts, history, rollups, retention, and threshold alerts
for free — and your number shows up in *House vitals* next to everyone else's.

```python
# Once, at setup. Thresholds are what turn a number into an alert.
telemetry.define_series(
    "body.weight", "Weight",
    unit="kg", app_slug="health", category="health",
    member=member, direction="down",     # up|down|range|neutral
    warn_above=90, alert_above=95,
    show_on_wall=False, precision=1,
) -> Series

# Whenever you have a reading.
telemetry.record_reading("body.weight", 74.2, member=member, app_slug="health")
telemetry.series_history("body.weight", hours=24*30, limit=500)
```

Keys are dotted and namespaced: `body.weight`, `house.living_room.temp`,
`nora.battery`, `money.portfolio`. Crossing a threshold fires
`core.signals.threshold_crossed` **and** notifies — you do not wire that up yourself.

`record_reading()` auto-creates a series if it does not exist, so a quick prototype
works before you have written `define_series()` — but without it you get no unit, no
thresholds, and an auto-titled label.

---

## Dashboard widgets

`from nora_home.dashboard.widgets import ChartWidget, StatWidget, ListWidget, TemplateWidget`

**Widgets return data, not HTML.** That is what keeps every chart in the house
looking like one system no matter who wrote the app. Declare them in `apps.py`
(`nora_widgets = [...]`) and they appear in the "Add a widget" picker for everyone.

| Base class | Implement | Returns |
|---|---|---|
| `ChartWidget` | `option(request)` | An ECharts option dict; the platform applies the house theme |
| `StatWidget` | `stat(request)` | `{"value", "unit", "label", "delta", "status", "spark": [...]}` |
| `ListWidget` | `rows(request)` | `[{"title", "meta", "status", "url", "action_url"}, ...]` |
| `TemplateWidget` | `context(request)` | Context for your own template — the escape hatch |

Class attributes: `title`, `subtitle`, `description`, `icon`, `default_size=(w, h)`,
`refresh_seconds`, `empty_message`.

```python
from nora_home.core.registry import scope_members

class WeekVolumeWidget(ChartWidget):
    title = "Volume this week"
    default_size = (4, 3)
    refresh_seconds = 300

    def option(self, request):
        members = scope_members(request)   # honours the "Everyone" switcher
        ...
        return {"xAxis": {...}, "series": [...]}
```

Use `scope_members(request)` rather than `request.user` — it returns just the viewer
normally, and every active member when someone has picked "Everyone", so your widget
gets the combined household view for free.

---

## Displays

`from nora_home.displays.bus import send_to_display, broadcast`

The 24" wall mirrors a real page of the app; the 10.1" kiosk is its remote control.

| Function | Does |
|---|---|
| `send_to_display(slug, payload) -> bool` | Send one message to one screen |
| `broadcast(payload) -> bool` | Send to every screen |

Message types the wall (`wall-live.js`) actually implements — anything else is
accepted by the bus and silently ignored in the browser:

| `type` | Effect |
|---|---|
| `navigate` | Point the wall's iframe at `path` |
| `refresh` | Reload the wall page |
| `banner` | Take over the top of the wall with an alert |

You will rarely call this directly. To put an alert on the wall, send a notification
with the `display` channel and let the platform do it.

**Kiosk buttons.** Declare `nora_kiosk_controls` in your `apps.py` and your app gets
its own button screen on the 10.1", swapped in the moment someone sends the wall to
your app:

```python
nora_kiosk_controls = [
    {"title": "Log a set", "path": "/workout/log/"},
    {"title": "This week", "path": "/workout/week/"},
]
```

---

## AI

`from nora_home.ai.client import ask, stream, AIUnavailable`

Claude, wired into the house, with a shared prompt-cached system prefix, per-call
cost accounting, and a monthly budget that refuses rather than overspends.

```python
from nora_home.ai import catalog

result = ask(
    "Summarise this week's workouts in two sentences.",
    context=json_blob,           # goes after the cache breakpoint
    app_slug="workout",
    tier=catalog.HOUSE,          # catalog.FAST | catalog.HOUSE | catalog.DEEP
    member=request.user,
)
result.text, result.model, result.cost_usd, result.duration_ms, result.refused
```

| Tier | For |
|---|---|
| `catalog.FAST` | Cheap, high-volume, latency-sensitive |
| `catalog.HOUSE` | The default |
| `catalog.DEEP` | Hard reasoning, worth the money |

Ask for a **tier**, never a model ID — the catalogue maps tiers to models in one
place so the house can be re-pointed at a newer model without touching your app.
Always handle `AIUnavailable` (no key, or budget exhausted); the house must degrade,
not break.

> **Status:** built, never run against a live API key — Story 13 on the dashboard.
> The Assistant page is deliberately not in the nav until it has been proven.

---

## Datastores

Both are **optional**. The house runs degraded, not broken, without them — catch the
unavailable exception and carry on.

```python
from nora_home.datastores import mongo, objects

mongo.put_document("workout_raw", {...}, app_slug="workout")   # MongoUnavailable
mongo.collection("workout_raw", app_slug="workout")
mongo.ensure_indexes("workout_raw", [...], app_slug="workout")

objects.put_bytes("progress/2026-08.png", data, app_slug="workout")  # StorageUnavailable
objects.get_bytes(key)
objects.put_file(key, path, app_slug="workout")
objects.presigned_url(key, expires=3600)
objects.delete(key)
```

**MySQL** for anything Todo joins across. **Mongo** for journals, transcripts,
raw integration payloads — where the shape changes without a migration. **Object
storage** for files. Keys are namespaced by `app_slug` for you.

---

## MCP

`from nora_home.mcpserver.registry import mcp_tool`

Expose your app's data as a tool an AI agent can call. Set
`nora_provides_mcp_tools = True` in `apps.py` and put the tools in `mcp_tools.py`.

```python
@mcp_tool(
    name="workout_week",
    description="Sets, reps and volume for the current week.",
    schema={"type": "object", "properties": {"member": {"type": "string"}}},
    scopes=["read"],           # read | write | admin
    app_slug="workout",
    dangerous=False,           # True = needs explicit confirmation
)
def workout_week(member: str = "") -> dict:
    ...
```

---

## Signals

`from nora_home.core.signals import ...`

How apps react to each other **without importing each other**.

| Signal | Fired by | Arguments |
|---|---|---|
| `item_completed` | todo | `item, member, completion` |
| `item_missed` | todo | `item, member, due_at` |
| `escalation_raised` | todo | `item, level, notified` |
| `threshold_crossed` | telemetry | `series, value, threshold, direction` |
| `integration_synced` | integrations | `integration, records, duration_ms` |
| `home_should_react` | anything | `mood, message, surface` |

```python
from django.dispatch import receiver
from nora_home.core.signals import item_completed

@receiver(item_completed)
def celebrate(sender, item, member, **kwargs):
    ...
```

**From Todo, `item` and `completion` are the same object** — the `Instance`,
which already carries the note and the actual minutes a receiver would want, so
there is no separate completion row as the deleted tracker had. It fires **once**, at the
moment the occasion genuinely becomes done: on `complete()` for an ordinary task,
on `approve()` for one with an approver, and not at all when someone amends an
occasion that was already finished.

---

## The rule

**Call the spine directly. Never import a peer app's models.**

`nora_home.todo`, `nora_home.notifications`, `nora_home.telemetry`,
`nora_home.ai`, `nora_home.datastores`, `nora_home.displays` and
`nora_home.core` are the platform. Importing `nora_home.todo.api` is correct and
expected — that is what it is for.

`houseapps.workout` importing `houseapps.family.models` is not. It makes both apps
undeletable: uninstall one and the other crashes at import time. Announce with a
signal, or record through telemetry, and let the other app listen.

If two of your apps genuinely need to share a table, that is one app.
