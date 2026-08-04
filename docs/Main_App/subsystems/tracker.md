# Tracker — `nora_home.tracker`

## What it is

The scheduling and accountability spine. Anything in the house that has to happen —
a habit, a filter change, a bill, a med — becomes a **trackable**, and the tracker
owns recurrence, whether it happened, and who hears about it when it didn't.

This is the single most reusable thing in the platform. An app that builds its own
due dates and reminders is doing it wrong.

## Status

**Built, unproven.** The models, materialisation, and ladder are written and
reviewed; no escalation has been observed running end to end on the Pi against a
real overdue item. Celery worker/beat health was never confirmed either — see
[`../progress.md`](../progress.md).

## Models

| Model | Holds |
|---|---|
| `Trackable` | The definition: title, owner, cadence, due time, policy, tags, `app_slug` + `source_ref` |
| `Occurrence` | One concrete due instance, materialised ahead of time |
| `Completion` | Someone did it — when, who, optional note and evidence |
| `EscalationPolicy` | The ladder, as editable JSON. Not code |
| `EscalationEvent` | An audit trail of which rung was reached, and who was told |
| `Cadence` | Choices: `once`, `daily`, `weekdays`, `weekly`, `monthly`, `quarterly`, `yearly`, `interval`, `cron` |

**Occurrences are materialised, not computed.** Concrete rows are written two weeks
ahead. That is what makes *"what did I miss last March"* answerable, and gives
escalation state somewhere to live. See [`../../CLAUDE.md`](../../../CLAUDE.md) § 4.

## The ladder

`EscalationPolicy.levels` is JSON, so the ladder is editable in `/admin/` without a
deploy. Three ship by default: **House default**, **Gentle**, **Safety critical**.
Each rung says how long to wait and who to tell — owner, then the person's
escalation chain, then every adult, then the whole house and the wall.

## What it offers other apps

`nora_home.tracker.api` — `register_trackable()`, `deactivate_trackable()`,
`complete_source()`, `open_items_for()`. Signatures in
[`../cross-functionality.md`](../cross-functionality.md#tracker).

Fires `item_completed`, `item_missed` and `escalation_raised` on
`nora_home.core.signals`, which is how other apps react without importing anything.

Widgets offered to the home screen: `TodayWidget`, `OverdueWidget`,
`ReliabilityWidget`, `StreakWidget`. Wall panel: `WallAgendaPanel`.
Provides MCP tools.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `materialize_schedules` | hourly, :05 | Writes upcoming occurrences two weeks ahead |
| `sweep_due_items` | every 5 min | Marks what is now overdue |
| `run_escalations` | every 5 min | Walks the ladder for anything still undone |

## Settings

None of its own. Escalation behaviour is data (`EscalationPolicy`), not config.

## Known gaps

- Not in the sidebar (`nora_nav = False`). The Today / Overdue / Reliability cards
  on the home dashboard are how the house actually uses it; the standalone page was
  removed as redundant.
- No tests (Story 21).
- Escalation has never been watched firing on real hardware.

## Files

```
models.py      Trackable, Occurrence, Completion, EscalationPolicy, EscalationEvent
api.py         the published surface other apps call
schedules.py   cadence -> concrete dates
escalation.py  the ladder engine
tasks.py       materialize / sweep / escalate
widgets.py     Today, Overdue, Reliability, Streak
cards.py       WallAgendaPanel
```
