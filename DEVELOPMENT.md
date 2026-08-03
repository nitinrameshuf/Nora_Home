# DEVELOPMENT.md — writing an app for Nora Home

**This file is for you if you are building an app that runs inside Nora Home** —
whether you are a person or an AI agent working on their behalf. Read it start to
finish before writing code. It is short on purpose.

If you want to know what Nora Home *is*, read [`CLAUDE.md`](CLAUDE.md) instead.

---

## The one idea

Nora Home is a platform. Your app should be **small**, because the platform already
does the hard parts:

| You might be tempted to build | Use this instead |
|---|---|
| Reminders, due dates, "did they do it" | `nora_home.tracker.api.register_trackable()` |
| Nagging people who forget | The escalation ladder — automatic |
| Slack messages | `nora_home.notifications.api.notify()` |
| A charts table and a chart library | `nora_home.telemetry.api.record_reading()` + a `ChartWidget` |
| Calling Claude | `nora_home.ai.client.ask()` |
| File uploads to S3 | A normal Django `FileField` |
| A cron job | `@shared_task` + a PeriodicTask row |
| An audit trail | `nora_home.core.audit.record()` |
| A private table in another app's domain | That app's `app_slug` through `tracker`/`telemetry` — see [Talking to other apps](#talking-to-other-apps) |
| Exposing your data to AI agents | `@mcp_tool` |
| Login, roles, who lives here | `settings.AUTH_USER_MODEL` |

**A good house app is mostly models and views.** If yours is growing a scheduler or a
notification queue, stop — the platform has one, and using it is what makes your app
show up on the wall display and in the family's Slack without extra work.

---

## Ten-minute start

The reference app refers to itself by name in more places than you'd guess — its
own module path is imported in seven files, and its templates live in a directory
named after it. Copy it, then do the rename in one mechanical pass rather than
hunting file by file (skipping this step doesn't fail loudly — it fails as
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
3. `models.py` — your models. Delete the habit ones. Note `app_slug="habits"` in
   the tracker registration call is a separate string from the URL slug; change it
   too.
4. `views.py` / `urls.py` — your pages. They mount at `/workout/` automatically.
5. Register it and migrate:

```bash
python manage.py install_app houseapps.workout
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
    nora_wall_panels = ["houseapps.workout.widgets.WallSummary"]
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

---

## Tracking, reminders, and escalation

Do not write reminder logic. Register a trackable and the platform owns due dates,
nudges, missed-item detection, streaks, and the escalation ladder.

```python
from nora_home.tracker.api import register_trackable, complete_source, deactivate_trackable


class Routine(OwnedModel):
    ...

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if not self.is_active:
            deactivate_trackable(app_slug="workout", source_ref=str(self.pk))
            return

        register_trackable(
            owner=self.owner,
            title=self.name,
            app_slug="workout",
            source_ref=str(self.pk),        # your own id — makes this idempotent
            cadence="weekly",               # once|daily|weekdays|weekly|monthly|
                                            # quarterly|yearly|interval|cron
            due_time=self.due_time,
            url=f"/workout/{self.uuid}/",   # deep link used by alerts and Slack
            kind="task",                    # task|habit|maintenance|goal|
                                            # measurement|checkin
            escalation_policy="House default",   # or "Gentle" / "Safety critical"
            requires_evidence=False,
        )
```

Calling `register_trackable` twice with the same `(app_slug, source_ref)` **updates**
rather than duplicating, which is why putting it in `save()` is safe.

When someone finishes the thing, tell the platform:

```python
complete_source(app_slug="workout", source_ref=str(routine.pk),
                member=request.user, note="Felt strong", value=8100)
```

That is what stops the nagging, extends the streak, and clears the wall display.

This is also the entire mechanism behind the home screen's "Today", "Overdue", and
"Reliability" widgets (`nora_home.tracker.widgets`) — they query every open/overdue
`Occurrence` in the house with **no `app_slug` filter at all**. The moment you call
`register_trackable`, your app's items appear in everyone's cross-app summary for
free. You do not write an aggregation widget; the platform already has one, and
`register_trackable` is how you opt in.

### The escalation ladder

Attached to every trackable via its policy. Ships with three:

| Policy | Behaviour |
|---|---|
| `House default` | nudge owner → warn owner (2h) → tell their contacts (12h) → tell the whole house (48h) |
| `Gentle` | one quiet note, one nudge 8h later, then let it go — for habits |
| `Safety critical` | warn owner → all adults at 15 min → whole house at 1h |

Policies are rows, editable in the admin. Add your own there rather than in code.

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

## The 24" wall and the 10.1" touchscreen

Two physical screens in the house work together, and most apps get useful
behaviour on both without any extra code:

- The **24" wall** shows the real app — whatever page is currently open,
  full-size, for anyone in the room to read. It has no touch or mouse.
- The **10.1" kiosk** is the remote control for it. It never shows your
  app's pages itself — it's a fixed grid of buttons. Tapping one switches
  what the wall is showing.

Every app with `nora_nav = True` already gets one kiosk button for free — it
switches the wall to your app's front page (`nora_url_prefix`). If your app
has more than one place worth jumping straight to, declare
`nora_kiosk_controls` in `apps.py` (shown above) and the kiosk grows a
whole screen of buttons for your app — tapping any of them still switches
the wall, just to that specific page instead of the front page. No websocket
code, no JavaScript, nothing else to wire up; the platform's existing
display bus (`nora_home/displays/`) carries the command.

Paths are plain strings, the same convention `nora_url_prefix` already uses
— not Django URL names needing `reverse()`.

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

Same free-aggregation pattern as tracker: `nora_home.telemetry.widgets.HouseVitalsWidget`
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
reaching into a "todo app." There isn't one — `tracker` **is** the house's
shared todo/scheduling spine, the same way `telemetry` is the shared numbers
store. Every app already has direct access to both:

```python
# From anywhere in your workout app:
from nora_home.tracker.api import register_trackable

register_trackable(
    owner=member,
    title="Log yesterday's session",
    app_slug="workout",              # still yours — this is what makes it
    source_ref=f"missed-log:{session.pk}",   #   "your" item on the shared board
    cadence="once",
    due_time=tomorrow_9am,
)
```

This is not a special case — it's the normal way to use tracker/telemetry/
notifications, which exist precisely so apps don't need private versions of
"things due" or "numbers over time." `app_slug` records *which app this item
belongs to* (for its icon, its URL, its place in the nav); it does not gate
who is allowed to create it. Calling these three APIs is always fine, from
any app, for your own data.

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
own with `django.dispatch.Signal`) is the escape hatch when tracker/telemetry/
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

- [ ] `apps.py` subclasses `NoraAppConfig` with a slug, title, description, category
- [ ] Migrations generated and committed
- [ ] Renders correctly at 375px and 1920px
- [ ] At least one widget offered to the home dashboard
- [ ] Anything with a deadline registers a trackable rather than reminding people itself
- [ ] Anything numeric and time-varying goes to telemetry
- [ ] An MCP tool for the data an agent would want, with a "call this when…" description
- [ ] No secrets outside `.env`; no direct imports of other apps' models
- [ ] Failures log and degrade rather than 500
- [ ] `python manage.py check` is clean
