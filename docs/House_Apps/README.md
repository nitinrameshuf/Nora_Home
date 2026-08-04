# docs/House_Apps/

One folder per app **the family wrote**. Not the platform's own subsystems — those
live in [`../Main_App/subsystems/`](../Main_App/subsystems/).

```
House_Apps/
├── README.md            you are here — the index and the required sections
└── <app-name>/          one folder per app
    ├── README.md        the app's main doc; diagrams and notes go here too
    └── testing.md       what its own tests cover, and what still needs a screen
```

**Both files are required.** `install_app` warns when either is missing, and
`tests/test_house_apps.py` fails without them. Copy
[`example_habit/README.md`](example_habit/README.md) and
[`example_habit/testing.md`](example_habit/testing.md) — the second is written as
the template, and explains which checks the platform already runs for you so you
do not write them again.

An app's folder is named after its module (`houseapps.workout` → `workout/`) and is
the place for **all** of that app's documentation — not only the README.
Screenshots, data-model notes, a decision log: put them in the app's own folder
rather than loose in `docs/`.

## Installed in this house

| App | Module | Docs | Status |
|---|---|---|---|
| _(none)_ | | | |

`NORA_HOME_HOUSE_APPS` is currently empty, so the house has no family apps
installed and the Apps page is deliberately blank.

| Reference | Module | Docs |
|---|---|---|
| Habits | `houseapps.example_habit` | [`example_habit/`](example_habit/README.md) |

The reference app is on disk to be **copied**, not run. It is also the template for
this documentation.

## Enforced at install time

`install_app` checks for `docs/House_Apps/<name>/README.md` and warns when it is
missing, so the requirement is real rather than only stated here. It warns rather
than refuses — a missing doc is a documentation problem, and blocking a working
install over it would just teach people to commit an empty file.

## Required sections

Every house app's README uses these headings, so any of them can be read the same
way. Copy [`example_habit/README.md`](example_habit/README.md) as the shape.

| Section | Answers |
|---|---|
| **What it is** | One paragraph. What problem in this house does it solve? |
| **Status** | Complete / built, unproven / planned — the vocabulary in [`../README.md`](../README.md) |
| **Who it is for** | Which roles, and whether data is per-person or house-wide |
| **Where it appears** | Nav, home dashboard, 24" wall, 10.1" kiosk, phone |
| **Data it owns** | Its models, and what it deliberately does *not* store because the platform does |
| **What it uses from the platform** | tracker / notifications / telemetry / AI / storage |
| **What it offers other apps** | Telemetry series, MCP tools, signals — see [`../Main_App/cross-functionality.md`](../Main_App/cross-functionality.md) |
| **Background work** | Celery tasks and their schedules |
| **Settings and secrets** | `.env` keys it needs. Say "none" if none |
| **Known gaps** | What is missing or unproven. Be honest — this is the most useful section |
| **Files** | A short map of the app directory |

## Adding an app

See [`../Main_App/DEVELOPMENT.md`](../Main_App/DEVELOPMENT.md) § Ten-minute start.
When you install one, create its folder here and add a row to the table above **in
the same commit**.
