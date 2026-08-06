# cross-functionality.md — what each app offers every other app

**The point of this file.** Nora Home is a platform. An app should almost never
build scheduling, reminders, escalation, notifications, charts, storage, or AI for
itself — the platform already has all of it, and using the shared version is what
makes a new app feel like part of the house instead of a website that happens to be
hosted next to one.

This is the index of everything one app may call from another. If you want a
capability and it is listed here, call it. If it is not listed here, it is not a
public surface — see [§ The rule](#the-rule) at the bottom.

Signatures below are copied from the code, not from memory. When you change a
published function, change its row here in the same commit.

---

## At a glance

| You want to… | Call | Lives in |
|---|---|---|
| Make something show up as due / overdue / escalating | `tracker.api.register_trackable()` | [Tracker](#tracker) |
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

## Tracker

`from nora_home.tracker import api as tracker`

The scheduling and accountability spine. Give it a thing that has to happen and it
handles recurrence, materialized occurrences, "what did I miss last March", and the
escalation ladder when nobody does it.

```python
tracker.register_trackable(
    owner=member,                  # HouseMember
    title="Change the water filter",
    app_slug="maintenance",        # yours
    source_ref="filter-kitchen",   # your record's stable id; re-calling updates
    cadence="interval",            # once|daily|weekdays|weekly|monthly|
                                   # quarterly|yearly|interval|cron
    interval_days=90,
    url="/maintenance/filters/3/", # where a person should land from a reminder
    escalation_policy="House default",
    show_on_wall=True,
    priority=2,
) -> Trackable
```

| Function | Does |
|---|---|
| `register_trackable(**kw) -> Trackable` | Create **or update** — keyed on `(app_slug, source_ref)`, so calling it again on save is the correct pattern, not a duplicate |
| `deactivate_trackable(*, app_slug, source_ref) -> int` | Stop tracking, keep history. Cancels pending occurrences so nothing escalates about a record you already deleted |
| `complete_source(*, app_slug, source_ref, member=None, note="", ...)` | Mark done from your side (e.g. the user ticked it in *your* UI, not the tracker's) |
| `open_items_for(member, limit=50)` | What this person currently owes the house |

**Reading back what happened.** These exist so you never have to import
`nora_home.tracker.models` — see [The rule](#the-rule). If you find yourself
wanting a query these do not cover, add a function here rather than reaching into
the models; that is what was done on 2026-08-04, when the reference app was still
importing them in five files and every app copied from it inherited the violation.

| Function | Does |
|---|---|
| `streak_for(*, app_slug, source_ref) -> int` | Consecutive completions on your record, until a miss. `0` for a record the tracker has never seen |
| `is_done_today(*, app_slug, source_ref) -> bool` | Completed today, in house-local time — what greys out your "done" button |
| `history_for(*, app_slug, source_ref, limit=60)` | That record's occurrences, newest first, for a detail page or chart |
| `completion_stats(*, app_slug, members=None, since=None, until=None) -> dict` | `{"done", "missed", "total", "rate"}`. `rate` is a percentage, or **`None`** when nothing was due — a gap in a chart is honest, a zero says "you failed" when there was nothing to do. Ignores still-pending work |
| `trackable_for(*, app_slug, source_ref)` | The `Trackable` itself, read-only. Prefer the others; this is the escape hatch |

**Cadences:** `once`, `daily`, `weekdays`, `weekly`, `monthly`, `quarterly`,
`yearly`, `interval` (+`interval_days`), `cron` (+`cron_expression`).

**Escalation** is a policy object, not code — `escalation_policy=` takes a name
string or an `EscalationPolicy`. Three ship by default: *House default*, *Gentle*,
*Safety critical*. They are editable in `/admin/` without a deploy.

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
- `nora_home.todo.escalation` — `escalate_due_instances()`, ported from
  `nora_home.tracker.escalation` onto `Instance`. Chases the owner alone,
  never the assignees — see `todo.md` §9.

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

**Channels:** `slack`, `inapp`, `display` (the 24" wall), `console`. Pass
`channels=[...]` only to force one — normally let the platform resolve it.

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

**MySQL** for anything the tracker joins across. **Mongo** for journals, transcripts,
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
| `item_completed` | tracker, todo | `item, member, completion` |
| `item_missed` | tracker, todo | `item, member, due_at` |
| `escalation_raised` | tracker | `item, level, notified` |
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
there is no separate completion row as the tracker has. It fires **once**, at the
moment the occasion genuinely becomes done: on `complete()` for an ordinary task,
on `approve()` for one with an approver, and not at all when someone amends an
occasion that was already finished.

---

## The rule

**Call the spine directly. Never import a peer app's models.**

`nora_home.tracker`, `nora_home.notifications`, `nora_home.telemetry`,
`nora_home.ai`, `nora_home.datastores`, `nora_home.displays` and
`nora_home.core` are the platform. Importing `nora_home.tracker.api` is correct and
expected — that is what it is for.

`houseapps.workout` importing `houseapps.family.models` is not. It makes both apps
undeletable: uninstall one and the other crashes at import time. Announce with a
signal, or record through telemetry, and let the other app listen.

If two of your apps genuinely need to share a table, that is one app.
