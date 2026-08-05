# requirements.md — Habits (`houseapps.example_habit`)

**This file is also the template.** Every house app needs one, and it is **gate 1**:
it is written *before any code*, and the user approves the functionality in it
before development starts. See
[`../../Main_App/DEVELOPMENT.md`](../../Main_App/DEVELOPMENT.md) § The workflow.

Copy this file, keep the headings, replace the content. Write it in language a
family member can check without reading code — if a section can only be understood
by someone who has seen the schema, it is written wrong.

> **Status: approved** — this is the reference app, written to demonstrate the
> contract. A real app records the date and who approved it here, so "did we agree
> to this?" has an answer later.

---

## The problem, and who it is for

People in the house want to do small things consistently — stretch, read, take
vitamins — and the thing that actually breaks consistency is forgetting, not
unwillingness. Anyone in the house can use it, including kids, so nothing may
require reading a chart to understand.

## What someone can do with it

The concrete list. Each line is something a person does, not something the system has.

- Add a habit with a title, a reason ("because my back hurts"), and a cadence of
  daily, weekdays, or weekly.
- Mark today's habit done, from a phone or from the app page.
- See their current streak, and how consistent they have been recently.
- See everyone's streaks together, on the wall display.

## What it tracks, reminds about, and escalates

| | |
|---|---|
| Cadence | Daily, weekdays, or weekly — chosen per habit |
| Due time | Optional per habit; otherwise the house default (18:00) |
| Reminder | The platform nudges the owner when an occurrence goes overdue |
| Escalation | House default ladder: owner → owner again → chain → house |
| Grace | A daily habit is *missed* one day after it was due |

**It does not implement any of this itself.** It registers a trackable and lets the
platform own the schedule — that is the pattern every house app should follow.

## What it shows on each surface

Answer for all five, including where the answer is "nothing".

| Surface | Shows |
|---|---|
| 24" wall | A streaks panel — who is on a run, read from ~3 metres |
| 10.1" kiosk | One tile, "Habits", switching the wall to the habits page; one control, "All habits" |
| Phone | The full app: add a habit, mark done, see a streak |
| Tablet | Same as phone |
| Laptop | Same as phone, plus two widgets offered to the home dashboard |

## What it deliberately does not do

Being explicit here is what keeps an app small.

- No reminder, notification, or escalation logic of its own.
- No history table — completions live in the tracker.
- No goal-setting, rewards, or streak-freeze mechanics.
- No per-habit charts beyond the two offered widgets.

## What data it owns, and what it needs from others

**Owns:** one `Habit` record per habit — title, why, cadence, due time, weekly
target, active flag. Nothing else.

**Needs from the platform:**

| From | For |
|---|---|
| `tracker.api.register_trackable()` | Due dates, streaks, escalation |
| `tracker.api.complete_source()` | Marking today done |
| `telemetry.api.record_reading()` | A weekly `habits.completion_rate` series |
| `notifications` | Reached indirectly, via escalation |
| `AUTH_USER_MODEL` | Who a habit belongs to |

**Needs from other house apps:** nothing. If your app does need something from a
peer, name it here and use its published API — never its models. See
[`../../Main_App/cross-functionality.md`](../../Main_App/cross-functionality.md).

## Open questions for the user

List anything you would otherwise guess at. This section is the point of the gate.

- _(none — this app is a reference implementation)_
