# Habits — `houseapps.example_habit`

> **This file is also the template.** Every house app is required to have a folder
> at `docs/House_Apps/<name>/` with a `README.md` using these sections.
> `install_app` warns when one is missing. Copy this file, delete what doesn't
> apply, and keep it honest — a section that says "none" is more useful than a
> section that lies.
>
> See [`../README.md`](../README.md) for the required sections and
> [`../../Main_App/DEVELOPMENT.md`](../../Main_App/DEVELOPMENT.md) for how to build
> an app in the first place.

---

## What it is

The reference house app: small things done daily, with streaks. It is deliberately
tiny but touches every part of the platform an app is likely to need — registry,
tracker, notifications, telemetry, widgets, a wall panel, an MCP tool, and a
Celery task.

**Status:** working reference implementation. Not currently installed in this
house — `NORA_HOME_HOUSE_APPS` is empty, so the family sees no Habits page. The
code stays on disk as the thing new apps get copied from.

## Who it is for

Anyone in the house. `nora_minimum_role` is unset, so the default (`member`)
applies — a kid sees it the same as an adult, and each person only sees their own
habits unless the switcher is set to "Everyone".

## Where it appears

| Surface | What shows |
|---|---|
| **Phone / laptop** | `/habits/` — the full list, tick to complete |
| **Home dashboard** | Two widgets: *Streak* and *Consistency* |
| **24" wall** | `HabitWallPanel` when the kiosk sends the wall to this app |
| **10.1" kiosk** | One button, *All habits*, via `nora_kiosk_controls` |
| **Nav** | Under *Self Improvement* (`Category.SELF`) |

## Data it owns

| Model | Holds |
|---|---|
| `Habit` | title, why, cadence, due time, weekly target, owner, active flag |

Completions are **not** stored here — they live in the tracker, which is the point.
`Habit.save()` calls `tracker.register_trackable()`, so scheduling, occurrences,
history, and escalation are the platform's job, not this app's.

## What it uses from the platform

| Uses | For |
|---|---|
| `tracker.api.register_trackable()` | Every habit becomes a trackable; the tracker owns recurrence and "did it happen" |
| `tracker.api.deactivate_trackable()` | Deactivating a habit stops it escalating |
| `notifications.api.notify()` | Streak milestones |
| `telemetry.api.record_reading()` | `habits.completion_rate`, so consistency charts and thresholds come free |
| `core.signals.item_completed` | Reacts when the tracker records a completion |
| `dashboard.widgets` | `StreakWidget` (stat), `ConsistencyWidget` (chart) |

## What it offers other apps

| Offers | How to use it |
|---|---|
| Telemetry series `habits.completion_rate` | Read it with `telemetry.api.series_history("habits.completion_rate")` — no import of this app needed |
| MCP tool `habit_streaks` | Any agent with a `read` scope can call it |
| Nothing else | No public Python API. Do **not** import `houseapps.example_habit.models` from another app — see [cross-functionality.md](../../Main_App/cross-functionality.md) |

## Background work

| Task | Schedule | Does |
|---|---|---|
| `tasks.record_completion_rate` | Daily | Writes yesterday's completion rate to telemetry |

## Settings and secrets

None. No API keys, no `.env` entries, no external services.

## Known gaps

- No tests — the platform has none either (Story 21).
- `target_per_week` is stored but only used by `ConsistencyWidget`; the tracker
  does not enforce it.

## Files

```
apps.py        the NoraAppConfig — the whole contract with the platform
models.py      Habit; save() registers it with the tracker
views.py       list + detail
urls.py        mounted at /habits/
widgets.py     StreakWidget, ConsistencyWidget
cards.py       HabitWallPanel
mcp_tools.py   habit_streaks
signals.py     listens for item_completed
tasks.py       daily telemetry write
admin.py       so an adult can fix data without a deploy
```
