# DEVELOPMENT.md — writing an app for Nora Home

**This file is for you if you are building an app that runs inside Nora Home** —
whether you are a person or an AI agent working on their behalf. Read it start to
finish before writing code. It is short on purpose.

| Also read | For |
|---|---|
| [`cross-functionality.md`](cross-functionality.md) | The full index of what every app can call from every other app — signatures, arguments, and the rule about never importing a peer app |
| [`../CLAUDE.md`](../../CLAUDE.md) | What Nora Home *is*, and why it is built this way |
| [`testing.md`](testing.md) | The test suite, and how to verify your app on the real hardware |
| [`architecture.md`](architecture.md) | How the pieces fit together, with diagrams |

---

## The workflow — three gates, in order

**Do not start with code.** Building a house app has three mandatory gates. Each one
has to be passed before the next begins, and gate 1 ends with a human saying yes.

### Gate 1 — Requirements, approved before any code is written

Write **`docs/House_Apps/<yourapp>/requirements.md`** first, describing what the app
*does* — not how it is built. There is no example to copy right now — the old
reference app was removed 2026-08-05 (see
[`subsystems/todo.md`](subsystems/todo.md) §1) — so use the required-sections
table in [`../House_Apps/README.md`](../House_Apps/README.md) directly.

It has to answer, in plain language a family member can check:

- What problem this solves, and who in the house it is for.
- What someone can actually do with it — the concrete list of actions.
- What it tracks, reminds about, or escalates, and on what cadence.
- What it shows on each of the five surfaces (24" wall, 10.1" kiosk, phone,
  tablet, laptop) — including "nothing" where that is the answer.
- What it deliberately does **not** do.
- What data it owns, and what it needs from other apps.

Then **stop and get approval on the functionality from the user.** Not on the
design, not on the schema — on whether the app should do these things. Writing an
app nobody wanted is the most expensive mistake available here, and it is entirely
avoidable by asking first. Coding begins only after that yes.

### Gate 2 — Development is not finished until it is tested and integrated

"It runs on my machine" is not the end of development. Before calling the app done,
both of these must hold:

1. **Unit tests for the app's own logic**, in `tests/test_<yourapp>.py`. The platform
   already contract-tests every installed app for you (see
   [Testing your app](#testing-your-app)) — what you add is the behaviour only your
   app knows about.
2. **Integration with the home app is verified**, not assumed. That means checking
   the seams your app actually uses:
   - Its tasks materialize and escalate (`todo`) — see the caveat in
     [Tracking, reminders, and escalation](#tracking-reminders-and-escalation).
   - Its notifications route and deliver (`notifications`).
   - Its readings land and its thresholds fire (`telemetry`).
   - Its widgets appear in the "Add a widget" picker and render on the home screen.
   - Its nav entry, kiosk tile, and any kiosk controls appear and go somewhere real.
   - `./scripts/run-tests.sh` is green — the whole suite, not only your file.

### Gate 3 — Deployed to the Pi, and checked over SSH

An app that has never run on the hardware is *built, unproven* — see the status
vocabulary in [`../../CLAUDE.md`](../../CLAUDE.md) § 0. Deploy it and confirm it,
using the access and commands in [`testing.md`](testing.md):

```bash
# on the Pi — everything operational goes through ./nora
cd ~/Nora_Home && ./nora upgrade

# then confirm, over SSH — do not assume
./nora manage check
./nora test                    # the suite, on the Pi
./nora app list                # your app is registered
./nora status                  # services and health
curl -sk https://localhost/<yourapp>/ -o /dev/null -w '%{http_code}\n'
```

Then look at the screens. Screenshot the wall and the kiosk (`testing.md`
§ Checking the real hardware) and confirm your app's tile is there and drives the
wall. **Only after that is the app Complete rather than built, unproven.**

---

## The one idea

Nora Home is a platform. Your app should be **small**, because the platform already
does the hard parts:

| You might be tempted to build | Use this instead |
|---|---|
| Reminders, due dates, "did they do it" | `nora_home.todo` — **but read [the caveat](#tracking-reminders-and-escalation) first: the app-facing call was deleted with the tracker and its successor is Story 24's to design** |
| Nagging people who forget | The escalation ladder — automatic |
| Slack messages | `nora_home.notifications.api.notify()` |
| Making the house say something out loud | `nora_home.notifications.speech.speak()` — synthesises, respects house-wide quiet hours, and gets the audio out to the host's speakers. Never call the TTS provider yourself: you would get correct audio, inside a container, that nobody can hear |
| A charts table and a chart library | `nora_home.telemetry.api.record_reading()` + a `ChartWidget` |
| Calling Claude | `nora_home.ai.client.ask()` |
| File uploads to S3 | A normal Django `FileField` |
| A cron job | `@shared_task` + a PeriodicTask row |
| An audit trail | `nora_home.core.audit.record()` |
| A private table in another app's domain | That app's `app_slug` through `todo`/`telemetry` — see [Talking to other apps](#talking-to-other-apps) |
| Exposing your data to AI agents | `@mcp_tool` |
| Login, roles, who lives here | `settings.AUTH_USER_MODEL` |

**A good house app is mostly models and views.** If yours is growing a scheduler or a
notification queue, stop — the platform has one, and using it is what makes your app
show up on the wall display and in the family's Slack without extra work.

---

## Ten-minute start

> **This starts at gate 2.** Gate 1 — `requirements.md`, approved by the user —
> comes before any of it. See [The workflow](#the-workflow--three-gates-in-order).

> **The copy-from-the-reference-app shortcut below is currently unavailable.**
> `houseapps/example_habit` was removed 2026-08-05 as part of the Levels/Todo
> work (see [`subsystems/todo.md`](subsystems/todo.md) §1) — there is nothing to
> `cp -r` right now. Build from the `apps.py` contract above and
> `nora_home/dashboard/widgets.py` / `nora_home/core/cards.py` directly instead;
> the steps below (rename the pieces, register, migrate, write the three docs)
> still apply, just starting from a blank `houseapps/<yourapp>/` rather than a
> copy. This note goes away once a real family app exists to serve as the new
> reference (Story 24 on the dashboard) — commands below are left as-written
> for then.

When a reference app exists again, it will refer to itself by name in more
places than you'd guess — expect its own module path to be imported in several
files, and its templates to live in a directory named after it. Copy it, then do
the rename in one mechanical pass rather than hunting file by file (skipping
this step doesn't fail loudly — it fails as
`django.contrib.admin.exceptions.AlreadyRegistered` the first time the new app's
`admin.py` runs, because it's still registering the *original* app's model class):

```bash
cp -r houseapps/example_habit houseapps/workout
rm -rf houseapps/workout/migrations houseapps/workout/__pycache__
mv houseapps/workout/templates/example_habit houseapps/workout/templates/workout

# Every file in the copy still says `example_habit` somewhere — flip them all:
grep -rl example_habit houseapps/workout | xargs sed -i 's/example_habit/workout/g'
```

Then, in your new directory:

1. `apps.py` — set `verbose_name`, `nora_title`, `nora_description`, `nora_category`
   to your own app (the sed above already fixed the class name, `nora_slug`, and
   every internal import — those don't need touching).
2. `mcp_tools.py` — rename the tool's `name=` argument (e.g. `habit_streaks` →
   `workout_streaks`). Leaving it as-is doesn't crash — the registry logs
   `MCP tool 'X' is already registered; overwriting` and moves on — but it means
   your app's tool silently replaces the original's rather than existing alongside
   it.
3. `models.py` — your models. Delete the habit ones. Note `app_slug="habits"` is
   a separate string from the URL slug; change it too, wherever it appears.
4. `views.py` / `urls.py` — your pages. They mount at `/workout/` automatically.
5. **Write your app's docs.** Every house app needs three files under
   `docs/House_Apps/<app>/` — `install_app` warns without them and the contract
   tests fail:

```bash
mkdir -p docs/House_Apps/workout
# requirements.md should already exist from gate 1; write the other two
# against the Required sections table in ../House_Apps/README.md — what it
# is, where it appears, what it owns, what it offers, what its own tests cover
```

   The required sections are listed in
   [`../House_Apps/README.md`](../House_Apps/README.md). The *Known gaps* section is
   the one people actually thank you for.

6. Register it and migrate:

```bash
./nora app install houseapps.workout
```

That adds it to `NORA_HOME_HOUSE_APPS` in `.env`, generates and applies migrations, and
collects static files. Restart (`make restart`) and it is live at `/workout/`.

This whole sequence — copy, rename, `install_app` — is tested end-to-end against a
fresh clone as part of this platform's own verification, not just described.

`install_app` also commits `houseapps/workout/` into this platform repo's own git
history. That is what makes the app survive a fresh clone or a dead SD card —
without it, the app is just loose files that only ever existed on the one Pi that
ran the install.

### Uninstalling and reinstalling

```bash
python manage.py uninstall_app workout                       # unregister only
python manage.py uninstall_app workout --purge-data --yes    # + drop its tables
python manage.py uninstall_app workout --remove-files --yes  # + delete the code
```

Plain `uninstall_app workout` only takes it out of `NORA_HOME_HOUSE_APPS` — the
nav entry, dashboard cards, and URL mount disappear, but its code, migrations, and
database rows are untouched. `install_app houseapps.workout` (the module-path
form, not a git URL) re-registers it later with every row of data still there —
this is the normal "reinstall" path and it is non-destructive.

`--purge-data` and `--remove-files` are separate, both opt-in, both require
`--yes`. Purge without removing files if you want the code around to reinstall
against a clean slate; remove files without purging if you're moving the app to
a different install and want the data to survive until it's re-registered there.

---

## The contract: `apps.py`

This is the whole interface between your app and the platform.

```python
from nora_home.core.registry import Category, NoraAppConfig


class WorkoutConfig(NoraAppConfig):
    # Standard Django.
    name = "houseapps.workout"
    label = "workout"
    verbose_name = "Workout"

    # Identity. The slug becomes your URL: /workout/
    nora_slug = "workout"
    nora_title = "Workout"
    nora_description = "Lifts, runs, and how the week actually went."
    nora_icon = "dumbbell"
    nora_category = Category.FAMILY

    # Placement.
    nora_nav = True          # show in the sidebar
    nora_order = 20          # lower sorts first within the category
    nora_minimum_role = "member"   # member | adult | admin

    # What you contribute to shared screens.
    nora_widgets = ["houseapps.workout.widgets.WeeklyVolume"]
    nora_dashboard_cards = []

    # Buttons the 10.1" kiosk shows once someone switches the 24" wall to
    # this app. Optional — skip it and your app still gets a single tile
    # that just switches the wall to your app's front page.
    nora_kiosk_controls = [
        {"title": "Log a set", "path": "/workout/log/"},
        {"title": "History", "path": "/workout/history/"},
    ]

    # Truthful declarations — they drive the app directory and MCP listing.
    nora_provides_mcp_tools = True
    nora_owns_telemetry_series = ["workout.volume", "workout.sessions"]

    # Set False to keep an app installed but hidden while it is half-built.
    nora_enabled = True

    def ready(self):
        # Imports only. Anything touching the database here runs before
        # migrations and will break a fresh install.
        from houseapps.workout import mcp_tools, signals  # noqa: F401
```

Categories: `SELF`, `AMBITION`, `FAMILY`, `ROBOT`, `HOUSE`, `INTEGRATIONS`, `SYSTEM`.

Your slug cannot be one of `home`, `admin`, `api`, `mcp`, `static`, `media`, `ws`,
`accounts`, `app`, `health` — the platform owns those.

Every house app is **Level 3** — `nora_level` defaults to `3` and you never need
to set it. Levels are the platform's dependency rule (see
[`subsystems/todo.md`](subsystems/todo.md) §1): the one thing that matters to
you is that nothing at Level 1 (the base) or Level 2 (an app the base leans on,
like Todo) is ever allowed to import your app back — you can be uninstalled at
any time without anything above you breaking.

---

## Tracking, reminders, and escalation

> ### Read this before you plan an app around it
>
> **There is currently no app-facing call for this.** Until 2026-08-06 the
> platform published `nora_home.tracker.api.register_trackable()`: you handed it
> a thing that had to happen, keyed on `(app_slug, source_ref)`, and got due
> dates, nudges, missed-item detection, streaks and the escalation ladder for
> free. Story 40 deleted the tracker and Todo took over its job — but Todo's API
> is written for a person working a board, not for another app registering work,
> and **no successor to `register_trackable()` exists yet.**
>
> What that call should look like on Todo's model is a design question, not a
> mechanical port, so it is deliberately being settled by **Story 24** — the
> first real family app, which is the first thing that actually needs it.
>
> **So, for now:** if your app needs recurrence and escalation, say so in your
> `requirements.md` and raise it before you write code, rather than working
> around it. If you need something in the meantime, drive
> `nora_home.todo.api` directly — but understand that you are using an interface
> meant for the Todo UI, and it may change when the app-facing one lands.

Everything below describes the shape the platform provides once the call exists.
The **escalation ladder itself is real and unchanged** — it is
`nora_home.todo.escalation`, running against `todo.Instance` — so a task created
through `nora_home.todo.api` today does escalate.

### The escalation ladder

Attached to every task via its policy (`Task.escalation_policy`, opt-in per task
via `Task.escalation_enabled`). Ships with three:

| Policy | Behaviour |
|---|---|
| `House default` | nudge owner → warn owner (2h) → tell their contacts (12h) → tell the whole house (48h) |
| `Gentle` | one quiet note, one nudge 8h later, then let it go — for habits |
| `Safety critical` | warn owner → all adults at 15 min → whole house at 1h |

Policies are rows (`nora_home.todo.models.EscalationPolicy`), editable in the
admin. Add your own there rather than in code — that is the whole reason `levels`
is JSON.

### The cross-app summary widgets

The home screen's Todo widgets (`nora_home.todo.widgets` — "Open now", "Due
next", "Keeping at it") query every open `Instance` in the house with **no
`app_slug` filter at all**. Anything that reaches Todo appears in everyone's
cross-app summary for free; you never write an aggregation widget. The same
pattern applies to `nora_home.telemetry.widgets.HouseVitalsWidget` for numbers,
and that one *does* have a working app-facing call today —
`telemetry.api.record_reading()`.

---

## Notifications

```python
from nora_home.notifications.api import notify, notify_house

notify(member,
       title="Deload week starts Monday",
       body="Four hard weeks in a row. Drop the volume 40%.",
       severity="info",              # info|nudge|warning|alert|critical
       app_slug="workout",
       url="/workout/plan/",
       dedupe_key=f"deload:{plan.pk}")   # suppresses repeats for an hour

notify_house(title="Power outage", body="UPS on battery.", severity="critical",
             app_slug="house")
```

Routing, quiet hours, per-person channel preferences, delivery receipts, and retries
are handled. `alert` and `critical` deliberately ignore quiet hours; everything else
respects them.

---

## The five surfaces

The same pages have to work on a phone in a pocket, an iPad on the counter, a
laptop, the 24" wall across the room, and the 10.1" kiosk under someone's thumb.
**You write one set of templates.** The platform names the surface server-side
(`nora_home/ui/middleware.py`) and puts it on `<html data-surface="...">`, so CSS
and templates can respond without measuring viewports in JavaScript.

| `data-surface` | Device | Detected by | Design for |
|---|---|---|---|
| `wall` | 24" 1080p on HDMI-0, always on, wall-mounted | URL (`/home/displays/wall`) | **Read at ~3 metres.** Big type, high contrast, no controls — nobody can touch it |
| `kiosk` | 10.1" 1024×600 touchscreen on HDMI-1 | URL (`/home/displays/kiosk`) | **One thumb.** Big targets, no keyboard, no scrolling if avoidable |
| `phone` | iPhone / Android | User-Agent | One column, thumb-reachable, offline-tolerant |
| `tablet` | iPad | User-Agent | Two columns, touch targets |
| `desktop` | laptop or monitor | fallback | Full density, hover states, pointer |

A `nh_surface` cookie overrides detection, so you can force a mode to test one.
`request.nh_surface` and `request.nh_is_touch` are available in every view.

```css
/* Wall: read from across the room. */
:root[data-surface="wall"] .card { padding: 1.6rem 1.8rem; font-size: 1.3rem; }

/* Kiosk: thumbs, not cursors. */
:root[data-surface="kiosk"] .btn { min-height: 64px; font-size: 1.15rem; }
```

Sizing tokens already scale per surface — if you use `.card`, `.btn`, `.item-list`
and the `--step-*` type scale, you get most of this for free and should not need
surface-specific CSS at all. Reach for it only when the *layout* genuinely differs,
not to nudge a font size.

### Your app's own navigation

The sidebar shows the house's pages. **Inside your app, it shows yours first** —
declare them and they appear:

```python
nora_sections = [
    {"title": "Log a set", "path": "/workout/log/"},
    {"title": "This week",  "path": "/workout/week/"},
    {"title": "Settings",   "path": "/workout/settings/"},
]
```

Same shape as `nora_kiosk_controls`, different job, and deliberately a separate
list: the kiosk gets a handful of big touch targets for driving the wall, a
sidebar can afford every section you have.

**Without this your sub-pages are reachable only by typing a URL.** That is not
hypothetical — Todo shipped that way and nobody noticed until someone opened it
and asked how they were supposed to get to the calendar. The house's own nav
stays below yours, so "back to the house" is never something you have to build.

`tests/test_registry.py` walks every declared section and fails if one 404s: a
link that looks like navigation and dead-ends is worse than a missing one.

### Your app does not need to style itself to be readable

The house paints a living background — the real season, time of day and weather
— behind everything. **On the base app's pages that is the point** and it is
meant to be clearly seen. **Inside a house app it is not**: somebody who opened
your app came to use it, so the platform automatically makes your panes
near-opaque and the background settles into the background.

You get this for free from `data-app` on `<html>`, set from the URL. Use `.card`
and the house's own classes and it is already handled — do not add your own
opacity, and in particular do not add `backdrop-filter` to something sitting on
an already-opaque surface: it blurs an opaque parent for no visible result, and
this house runs on a Pi driving two screens continuously.

### How the two screens work together

- The **24" wall** shows the real app — whatever page is currently open, full-size,
  for anyone in the room to read. It has no touch and no mouse.
- The **10.1" kiosk** is the remote control for it. It never shows your app's pages
  itself; it is a fixed grid of buttons. Tapping one switches what the wall shows.

Every app with `nora_nav = True` already gets one kiosk button for free — it sends
the wall to your app's front page (`nora_url_prefix`). If your app has more than
one place worth jumping straight to, declare `nora_kiosk_controls` in `apps.py` and
the kiosk grows a whole screen of buttons for your app:

```python
nora_kiosk_controls = [
    {"title": "Log a set", "path": "/workout/log/"},
    {"title": "This week", "path": "/workout/week/"},
]
```

Paths are plain strings, the same convention `nora_url_prefix` uses — not Django
URL names needing `reverse()`. No websocket code and no JavaScript: the display bus
(`nora_home/displays/`) carries the command.

**What the wall actually implements** is `navigate`, `refresh` and `banner`
(`static/nora_home/js/wall-live.js`). The bus will happily relay anything else and
the browser will silently ignore it — if you invent a new message type, add the
handler in the same commit or you are shipping a button that does nothing.

### Phones: PWA, not a native app

Phones and iPads hit the same server over the LAN. There is deliberately no native
app — see [`../CLAUDE.md`](../../CLAUDE.md) § 5. The one real gap is background push on
iOS, which is why notifications are channel-agnostic and Slack carries anything
urgent. Do not build around a phone-only capability (Bluetooth, background
location, on-device ML) without raising it first.

### Everything must survive a dead network

The Pi has to work with the internet down. ECharts and Gridstack are **vendored**
into `static/nora_home/vendor/` for exactly this reason. **No npm, no bundler, no
framework, no CDN.** A family member's agent should be able to add a chart without
a toolchain, and the Pi should never run a build step.

---

## Charts and the home dashboard

The home screen is a grid each person arranges from widgets that apps offer. You
offer them; you never decide where they go.

```python
# houseapps/workout/widgets.py
from nora_home.dashboard.widgets import ChartWidget, ListWidget, StatWidget


class WeeklyVolume(ChartWidget):
    title = "Training volume"
    subtitle = "Last 12 weeks"
    description = "Total kg moved per week."   # shown in the widget picker
    default_size = (6, 4)                      # 12-column grid; a row is ~80px
    refresh_seconds = 600

    def option(self, request):
        weeks, volumes = weekly_volume(request.user)
        return {
            "xAxis": {"type": "category", "data": weeks},
            "yAxis": {"type": "value", "name": "kg"},
            "series": [{"type": "bar", "data": volumes}],
        }


class LastSession(StatWidget):
    title = "Last session"
    default_size = (3, 2)

    def stat(self, request):
        session = latest_for(request.user)
        return {"value": session.volume_kg, "unit": "kg", "label": session.name,
                "delta": "+4%", "status": "ok", "spark": session.recent_volumes()}
```

Return an **ECharts option dict** — the house theme, colours, fonts, and dark/light
handling are applied for you. Do not set colours yourself; that is what keeps every
chart in the house looking like one system.

Four widget types: `ChartWidget` (`option()`), `StatWidget` (`stat()`),
`ListWidget` (`rows()`), `TemplateWidget` (`template` + `context()`).

Keep these fast. Every visible widget renders on one page load, and the wall display
re-renders forever.

---

## Measurements over time

Anything that is "a number, at a time, maybe about a person" goes to telemetry.
Weight, sleep, room temperature, battery, portfolio value, litres of water.

```python
from nora_home.telemetry.api import define_series, record_reading

# Once, at setup — thresholds are what turn a number into an alert.
define_series("workout.volume", "Weekly volume", unit="kg", app_slug="workout",
              category="fitness",     # optional — groups across apps, not just yours
              direction="up", show_on_wall=True)

# Whenever you have a reading.
record_reading("workout.volume", 8100, member=member, source="manual")
```

Crossing a threshold fires a notification and the `threshold_crossed` signal
automatically. Recording here — rather than in your own table — is also what makes
the number visible to the AI, the MCP tools, and the wall display.

`category` is what a private metrics table could never give you: it lets the home
screen group your numbers with another app's by *theme* ("fitness", "health",
"house") instead of by which app happens to own them. Leave it blank and your series
still shows up everywhere, just grouped under its `app_slug` instead.

Same free-aggregation pattern as Todo's widgets: `nora_home.telemetry.widgets.HouseVitalsWidget`
queries every active `Series` with no `app_slug` filter, the same way `TodayWidget`
does for occurrences. Call `define_series`/`record_reading` and your number is on it —
no widget to write, nothing to register beyond the call you were already making.

---

## AI

```python
from nora_home.ai.client import ask, AIUnavailable
from nora_home.ai import catalog

try:
    answer = ask(
        "Given these five sessions, what is the one thing to change next week?",
        context=sessions_as_text,
        app_slug="workout",
        tier=catalog.DEEP,        # FAST | HOUSE | DEEP
    )
except AIUnavailable as exc:
    answer = None   # no key, over budget, or the API declined — degrade, don't 500
```

Never call the Anthropic SDK directly. Going through `ask()` gets you the shared
house system prompt (which is prompt-cached, so it is nearly free after the first
call), cost accounting against the monthly budget, and an audit row.

For anything the user is not sitting and waiting for, use the task:

```python
from nora_home.ai.tasks import ask_async

ask_async.apply_async(kwargs={
    "prompt": "Write this week's training summary.",
    "context": context, "app_slug": "workout",
    "member_id": member.pk, "title": "Your week in the gym",
}, queue="ai")
```

---

## Background work

Any `tasks.py` in an installed app is autodiscovered.

```python
from celery import shared_task


@shared_task(queue="apps")     # apps | ai | integrations — not platform or alerts
def recalculate_plans():
    ...
```

To run it on a schedule, add a **PeriodicTask** row in the admin
(Django Celery Beat → Periodic tasks). Do not edit `config/celery.py` — that is the
platform's clock, and keeping them separate means a family member can retime your job
without a deploy.

Queues are separated so a slow app task cannot delay an escalation. Use `apps`.

---

## Exposing your data to AI agents

```python
# houseapps/workout/mcp_tools.py
from nora_home.mcpserver.registry import mcp_tool


@mcp_tool(
    name="workout_history",
    description=(
        "A member's training sessions over a window of days, with volume and "
        "exercises. Call this when asked how someone's training is going, or "
        "before suggesting a change to their programme."
    ),
    schema={
        "type": "object",
        "properties": {
            "member": {"type": "string", "description": "Username."},
            "days": {"type": "integer", "description": "Look-back window."},
        },
        "required": ["member"],
    },
    app_slug="workout",
)
def workout_history(member: str, days: int = 30, **_):
    return [...]   # anything JSON-serialisable
```

Write the description to say **when to call it**, not just what it returns — that is
what makes an agent reach for it at the right moment.

Tools that change state must declare `scopes=["read", "write"]`; the HTTP transport
refuses them unless the caller's token carries that scope.

---

## Talking to other apps

### The shared spine isn't "another app" — call it directly

If you want your workout app to put something on a todo list, you are not
reaching into someone else's app. `nora_home.todo` **is** the house's shared
todo/scheduling spine, the same way `telemetry` is the shared numbers store, and
every app has direct access to both:

```python
# From anywhere in your workout app:
from nora_home.telemetry.api import record_reading

record_reading("workout.volume_kg", 8100, member=member, source="workout")
```

This is not a special case — it's the normal way to use todo/telemetry/
notifications, which exist precisely so apps don't need private versions of
"things due" or "numbers over time." `app_slug` records *which app this item
belongs to* (for its icon, its URL, its place in the nav); it does not gate
who is allowed to create it. Calling these APIs is always fine, from any app,
for your own data.

**The scheduling half of that promise has a hole in it right now.** The example
above used to be `register_trackable()`, which Story 40 removed along with the
tracker; see [Tracking, reminders, and
escalation](#tracking-reminders-and-escalation). Telemetry and notifications are
unaffected and work exactly as described.

### Peer apps: never import, only signal

What you must not do is reach into **another app's own models or private
logic** — e.g. importing `houseapps.mealplan.models.Recipe` from your workout
app to read its internals directly. If a genuinely separate app needs to
react to something your app does, it listens for a signal instead of your
app calling into it:

```python
from django.dispatch import receiver
from nora_home.core.signals import item_completed, threshold_crossed


@receiver(item_completed)
def on_completion(sender, item, member, completion, **kwargs):
    if item.trackable.app_slug != "workout":
        return          # always filter — this fires for every app in the house
    ...
```

Available: `item_completed`, `item_missed`, `escalation_raised`, `threshold_crossed`,
`integration_synced`, `home_should_react`. Firing one of these (or defining your
own with `django.dispatch.Signal`) is the escape hatch when todo/telemetry/
notifications don't already cover what you're announcing — it keeps two apps
decoupled: yours doesn't need to know the mealplan app exists, or even whether
anything is listening.

### Logs, audit, and alerts are not the same thing

Four different records exist in this platform, and mixing them up either
spams the family or loses the trail when something needs investigating:

| | Who sees it | Where it lives | Use for |
|---|---|---|---|
| Python `logging.getLogger(__name__)` | Nobody — developers only, on disk | `logs/nora.log` | Debugging, request tracing |
| `nora_home.core.audit.record()` | Nobody, unless someone goes looking | `AuditEvent` table, queryable | "What happened" — durable, never pushed, never edited |
| `nora_home.telemetry.api.record_reading()` | Nobody, until it crosses a threshold | `Series`/`Reading` tables | Numbers over time — silent by default |
| `nora_home.notifications.api.notify()`/`notify_house()` | The person or house it's addressed to, actively | `Notification` + `Delivery` | The only one of the four meant to interrupt someone |

The rule of thumb: **write an audit event for anything a family member might
later ask "wait, what happened here?" about** — a completion, a config
change, an app installed. **Only call `notify()` for something a person
should be told about now.** A threshold crossing on a telemetry reading is
the one built-in bridge between the silent tiers and the loud one — it
already fires a notification for you (see [Measurements over time](#measurements-over-time)) — everything else stays exactly as loud as you choose to make it.

---

## Models

```python
from nora_home.core.models import OwnedModel, SoftDeleteModel, TimeStampedModel, UUIDModel


class Session(UUIDModel, SoftDeleteModel, OwnedModel):
    """Inherit at minimum TimeStampedModel. OwnedModel adds `owner` and implies it."""
```

- `TimeStampedModel` — `created_at`, `updated_at`. Non-negotiable.
- `OwnedModel` — adds `owner` (a `HouseMember`). Use whenever it belongs to a person.
- `SoftDeleteModel` — `.delete()` sets `deleted_at`; `.objects.alive()` filters.
  Use when losing the record would hurt.
- `UUIDModel` — adds `uuid`. Use for anything referenced from outside the DB.

Reference people as `settings.AUTH_USER_MODEL`, never by importing `HouseMember`.

---

## Templates and styling

Extend `base.html` and use the existing classes — `card`, `card-grid`, `item`,
`item-list`, `pill`, `btn`, `tick`, `empty`. Do not ship your own colours or
type scale; the house has one and the wall display depends on it.

```html
{% extends "base.html" %}
{% block content %}
  <ul class="item-list">
    {% for session in sessions %}
      <li class="item">
        <div class="item-body">
          <div class="item-title">{{ session.name }}</div>
          <div class="item-meta">{{ session.volume_kg }} kg</div>
        </div>
      </li>
    {% endfor %}
  </ul>
{% endblock %}
```

Templates go in `houseapps/<yourapp>/templates/<yourapp>/`.

The template context already has `surface` (`wall` / `kiosk` / `phone` / `tablet` /
`desktop`), `is_touch`, `is_wall`, and `is_kiosk`. Use them when a screen genuinely
needs different content — not for layout, which the CSS already handles.

Your pages must work on a phone, an iPad, a laptop, and the 24" wall display. Test at
375px and at 1920px.

---

## Testing your app

The platform already tests a lot on your behalf. `tests/test_house_apps.py` walks
every installed app and checks it automatically — that its widgets and cards load,
that its page returns 200, that its kiosk controls resolve, that its models inherit
`TimeStampedModel`, that it has a migration, and that it obeys the two rules in
"What not to do" below about `os.environ` and other apps' models. **You get all of
that by existing.** Do not write it again.

What is left for you is your app's own logic. Put it in `tests/test_<yourapp>.py`,
so it appears as its own line in the report:

```python
"""Workout — sets, volume, and the weekly rollup."""

import pytest

from houseapps.workout.models import Session

pytestmark = pytest.mark.django_db


def test_logging_a_session_records_its_volume(member):
    """The platform owns the numbers store; this app only hands it the reading."""
    from nora_home.telemetry.models import Reading

    session = Session.objects.create(owner=member, title="Push day", volume_kg=8100)

    assert Reading.objects.filter(series__key="workout.volume_kg",
                                  value=8100).exists()
```

Fixtures from `tests/conftest.py` are available to you — `member`, `adult`,
`admin_member`, `household`, `make_member`, `policy`, `series`, `wall_display`,
`kiosk_display`, `signal_recorder`. Use them instead of building people by hand.

```bash
./scripts/run-tests.sh workout      # just yours
./scripts/run-tests.sh              # everything, before you push
```

### Two layers, and yours needs both

`./nora test` runs Python only. It never renders a page, never runs a line of
your JavaScript, and never looks at a pixel — which is precisely where this
project's most user-visible bugs have lived. "Add a widget" was broken for a day
with every unit test green.

So there is a second layer: **`./nora qa`**, which drives a real Chromium against
a running house. Put your app's browser tests in `tests/qa/test_<yourapp>_qa.py`:

```python
"""Workout — in a real browser."""

import pytest

from tests.qa.conftest import measure_text_contrast, open_actions_menu, visit

pytestmark = pytest.mark.qa


def test_logging_a_set_updates_the_page_without_a_reload(signed_in, console_errors):
    visit(signed_in, "/workout/")

    signed_in.locator("[data-log-set]").first.click()
    signed_in.wait_for_timeout(800)

    assert not console_errors, "logging a set threw: " + "; ".join(console_errors)
    assert "1 set" in signed_in.locator(".workout-today").inner_text()


def test_the_page_is_readable_on_the_kiosk(signed_in):
    signed_in.set_viewport_size({"width": 1024, "height": 600})
    visit(signed_in, "/workout/")

    assert measure_text_contrast(signed_in, ".card p") >= 4.5
```

Fixtures you get for free, from `tests/qa/conftest.py`:

| Fixture / helper | Gives you |
|---|---|
| `signed_in` | A page already signed in as a household member |
| `console_errors` | Everything the browser logged — assert it stays empty |
| `visit(page, path)` | Navigate and settle. **Use this, not `networkidle`** — the wall and kiosk hold websockets open, so the network is never idle and the wait times out |
| `open_actions_menu(page)` | Opens the profile dropdown, where page actions live |
| `measure_text_contrast(page, selector)` | Real contrast, measured from pixels |
| `house_url` | Whatever house the run is pointed at |

Run yours with `./nora qa` (add `-k workout` for just yours). It needs a running
house and takes minutes, not seconds — that is why it is a separate command.

**On contrast: measure pixels, not the DOM.** axe's own `color-contrast` rule is
switched off here, deliberately. It composites translucent panes onto the nearest
opaque ancestor, and this app paints a living gradient behind everything — so it
reported readable kiosk tiles as 1.95:1 against a grey that appears nowhere on
screen. Measured from the rendering, the same text is 18:1. Every *other* axe
rule is enforced, and they will check your pages automatically: a form field
with no label, an icon-only button, a link with no text.

**What neither layer can tell you:** whether the wall is legible from three
metres, whether the touchscreen is calibrated, or whether your app looks good.
Those are gate 3 — see [`testing.md`](testing.md) § Checking the real hardware.

---

Two house rules worth copying: **a test name is a sentence**
(`test_a_miss_breaks_the_streak`, not `test_streak_2`), and **nothing may depend on
the wall clock** — use fixed dates, because a test that passes all day and fails at
22:00 is worse than no test. Full detail, including how the compact report works
and what it deliberately does not cover, is in [`testing.md`](testing.md).

---

## What not to do

- **Do not import another app's models.** Signals and published APIs only.
- **Do not read `os.environ`.** Add a setting to `config/settings/base.py`.
- **Do not put secrets in the database.** `.env`, always.
- **Do not build your own reminders, cron, or notification queue.**
- **Do not call the Anthropic SDK directly.** Use `nora_home.ai.client`.
- **Do not add npm, a bundler, or a frontend framework.** The Pi does not build
  assets, and the house must work offline.
- **Do not use `queue="platform"` or `queue="alerts"`.** Those are the platform's.
- **Do not let a failure cascade.** Catch, log, degrade. The wall display must
  survive your app having a bad day.
- **Do not edit an applied migration.** Add a new one.

---

## Checklist before you call it done

**Gate 1 — agreed before any of this was written**

- [ ] **`docs/House_Apps/<yourapp>/requirements.md` written and approved by the
      user** — what the app does, in plain language, before the code existed

**Gate 2 — development**

- [ ] `apps.py` subclasses `NoraAppConfig` with a slug, title, description, category
- [ ] **`docs/House_Apps/<yourapp>/README.md` and `testing.md` written** — required;
      `install_app` warns and the contract tests fail without them. See
      [`../House_Apps/README.md`](../House_Apps/README.md) for the sections
- [ ] Migrations generated and committed
- [ ] Renders correctly at 375px **and** 1920px, and is readable on the 24" wall
- [ ] At least one widget offered to the home dashboard
- [ ] Kiosk controls declared if the app has more than one place worth jumping to
- [ ] Anything with a deadline registers a trackable rather than reminding people itself
- [ ] Anything numeric and time-varying goes to telemetry
- [ ] An MCP tool for the data an agent would want, with a "call this when…" description
- [ ] No secrets outside `.env`; no direct imports of other apps' models
- [ ] Failures log and degrade rather than 500
- [ ] `python manage.py check` is clean
- [ ] `./nora test` is green — including the house-app contract checks in
      `tests/test_house_apps.py`, which run against your app automatically
- [ ] Tests written for your app's own logic, in `tests/test_<yourapp>.py`
- [ ] Browser tests in `tests/qa/test_<yourapp>_qa.py`, and `./nora qa` green —
      the unit tests never run your JavaScript or render your page
- [ ] `docs/House_Apps/<yourapp>/README.md` **and** `testing.md` exist
- [ ] Integration with the platform verified, not assumed: trackables materialize
      and escalate, notifications deliver, readings land, widgets appear in the
      picker, and the nav entry and kiosk tile go somewhere real

**Gate 3 — the hardware**

- [ ] Deployed to the Pi and confirmed over SSH: `manage.py check`, the suite run
      *on the Pi*, `list_apps` showing your app, and its page returning 200
- [ ] Both screens screenshotted — your tile is on the kiosk and drives the wall
- [ ] Actually seen working — see [`testing.md`](testing.md), not just a diff.
      Until this is done the app is *built, unproven*, not Complete
