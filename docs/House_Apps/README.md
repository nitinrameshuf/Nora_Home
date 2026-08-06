# docs/House_Apps/

One folder per app **the family wrote**. Not the platform's own subsystems — those
live in [`../Main_App/subsystems/`](../Main_App/subsystems/).

```
House_Apps/
├── README.md            you are here — the index and the required sections
└── <app-name>/          one folder per app
    ├── requirements.md  what it does, approved BEFORE any code was written
    ├── README.md        the app's main doc; diagrams and notes go here too
    └── testing.md       what its own tests cover, and what still needs a screen
```

**All three are required.** `install_app` warns when any is missing, and
`tests/test_house_apps.py` fails without them. There is no reference app to copy
right now — `houseapps.example_habit` was removed 2026-08-05 as part of the
Levels/Todo work (see [`../Main_App/subsystems/todo.md`](../Main_App/subsystems/todo.md)
§1) and its own docs went with it. Until the first real family app lands
(Story 24 on the dashboard), use the **Required sections** table below directly
— it does not depend on having an example to copy from.

`requirements.md` comes **first, before any code**, and the user approves the
functionality in it before development starts. That is gate 1 of the three-gate
workflow in
[`../Main_App/DEVELOPMENT.md`](../Main_App/DEVELOPMENT.md#the-workflow--three-gates-in-order):

1. **Requirements, approved.** Write `requirements.md`, get a yes on *what the app
   does*, then start coding.
2. **Tested and integrated.** Unit tests for your own logic, plus verified
   integration with the platform — todo, notifications, telemetry, widgets, nav
   and kiosk. The whole suite green, not just your file.
3. **Deployed to the Pi and checked over SSH.** An app that has never run on the
   hardware is *built, unproven*, not Complete.

An app's folder is named after its module (`houseapps.workout` → `workout/`) and is
the place for **all** of that app's documentation — not only the README.
Screenshots, data-model notes, a decision log: put them in the app's own folder
rather than loose in `docs/`.

## Installed in this house

| App | Module | Docs | Status |
|---|---|---|---|
| _(none)_ | | | |

`NORA_HOME_HOUSE_APPS` is currently empty, so the house has no family apps
installed and the Apps page is deliberately blank. There is also no reference
app on disk any more — see the note above.

## Enforced at install time

`install_app` checks for `docs/House_Apps/<name>/README.md` and warns when it is
missing, so the requirement is real rather than only stated here. It warns rather
than refuses — a missing doc is a documentation problem, and blocking a working
install over it would just teach people to commit an empty file.

## Required sections

Every house app's README uses these headings, so any of them can be read the same
way.

| Section | Answers |
|---|---|
| **What it is** | One paragraph. What problem in this house does it solve? |
| **Status** | Complete / built, unproven / planned — the vocabulary in [`../README.md`](../README.md) |
| **Who it is for** | Which roles, and whether data is per-person or house-wide |
| **Where it appears** | Nav, home dashboard, 24" wall, 10.1" kiosk, phone |
| **Data it owns** | Its models, and what it deliberately does *not* store because the platform does |
| **What it uses from the platform** | todo / notifications / telemetry / AI / storage |
| **What it offers other apps** | Telemetry series, MCP tools, signals — see [`../Main_App/cross-functionality.md`](../Main_App/cross-functionality.md) |
| **Background work** | Celery tasks and their schedules |
| **Settings and secrets** | `.env` keys it needs. Say "none" if none |
| **Known gaps** | What is missing or unproven. Be honest — this is the most useful section |
| **Files** | A short map of the app directory |

## Adding an app

See [`../Main_App/DEVELOPMENT.md`](../Main_App/DEVELOPMENT.md) § Ten-minute start.
When you install one, create its folder here and add a row to the table above **in
the same commit**.
