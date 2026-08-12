# docs/

The project's own record of itself. **These files are part of the deliverable, not
an afterthought — when code changes, they change in the same commit.** See
[`../CLAUDE.md`](../CLAUDE.md) § 0, Documentation duty.

## How this folder is organised

Three folders, by **who the document is for**.

```
docs/
├── README.md          you are here — the map
│
├── User/              for people, not agents. The HTML views
│   ├── deployment.html            install / update / uninstall
│   └── dashboard/                 the story board — the main status view
│
├── Main_App/          the Django platform and its infrastructure
│   ├── DEVELOPMENT.md             how to write a house app
│   ├── cross-functionality.md     what every app offers every other app
│   ├── architecture.md            how the pieces fit together, with diagrams
│   ├── testing.md                 the test suite, and how to verify on real hardware
│   ├── progress.md                the narrative log, newest last
│   ├── found-by-the-user.md       what the user caught, not an agent
│   └── subsystems/                one file per platform subsystem
│
└── House_Apps/        the family's own apps
    ├── README.md                  the index, and the required sections
    └── <app-name>/                one folder per app, holding its docs
        ├── requirements.md        what it does — approved before any code
        ├── README.md              what it is and where it appears
        └── testing.md             what its tests cover, and what needs a screen
```

**The rule:** a document about the platform goes in `Main_App/`. A document about
one family app goes in `House_Apps/<app-name>/`. Anything meant to be *read* by a
person rather than an agent — the HTML views — goes in `User/`.

## Start here

| If you want to… | Read |
|---|---|
| Know what this project is and why | [`../CLAUDE.md`](../CLAUDE.md) |
| Install or update the house | [`User/deployment.html`](User/deployment.html) |
| See where the project stands | [`User/dashboard/nora_home_dashboard.html`](User/dashboard/nora_home_dashboard.html) |
| Build an app inside it | [`Main_App/DEVELOPMENT.md`](Main_App/DEVELOPMENT.md) |
| Use another app's capabilities | [`Main_App/cross-functionality.md`](Main_App/cross-functionality.md) |
| Understand one subsystem | [`Main_App/subsystems/`](Main_App/subsystems/) |
| Run the house — install, start, update, back up, apps | `./nora help`, and [`User/deployment.html`](User/deployment.html) |
| Run the tests, or verify your change actually works | [`Main_App/testing.md`](Main_App/testing.md) |
| Know what happened and when | [`Main_App/progress.md`](Main_App/progress.md) |
| Read about an installed family app | [`House_Apps/`](House_Apps/) |

## Every file, and when to update it

### User/ — for people

| File | What it is | Update when |
|---|---|---|
| [`User/dashboard/nora_home_dashboard.html`](User/dashboard/nora_home_dashboard.html) | **The main view.** Every story, its status, dependencies, files. Click a card for detail | A story changes status, or a new one is added |
| [`User/deployment.html`](User/deployment.html) | Install, update, uninstall, and what happens to data at each step | Deployment steps change |

### Main_App/ — the platform

| File | What it is | Update when |
|---|---|---|
| [`Main_App/progress.md`](Main_App/progress.md) | The narrative log — what happened, in order, with dates | Every working session that changes code |
| [`Main_App/found-by-the-user.md`](Main_App/found-by-the-user.md) | Bugs, invented rules and over-claims the user caught rather than an agent | When the user finds something an agent did not |
| [`Main_App/architecture.md`](Main_App/architecture.md) | How the system fits together, with Mermaid diagrams | A component, boundary, or data flow changes |
| [`Main_App/DEVELOPMENT.md`](Main_App/DEVELOPMENT.md) | The guide for anyone writing a house app | The app contract, surfaces, or platform APIs change |
| [`Main_App/cross-functionality.md`](Main_App/cross-functionality.md) | Index of every published cross-app API | You add, change, or remove a published function |
| [`Main_App/testing.md`](Main_App/testing.md) | The test suite, Pi access, the deploy loop, and how to check real hardware | The verification workflow changes, or a subsystem's coverage does |
| [`Main_App/subsystems/*.md`](Main_App/subsystems/) | One subsystem each — what it owns, its models, tasks, settings, gaps | That subsystem changes |

### House_Apps/ — the family's apps

| File | What it is | Update when |
|---|---|---|
| [`House_Apps/README.md`](House_Apps/README.md) | The index of installed apps, and the sections each one must document | An app is installed or removed |
| `House_Apps/<app>/README.md` | One app: what it is, where it appears, what it owns and offers | That app changes |

`install_app` warns when an app has no folder here, so the requirement is enforced
at install time rather than only stated.

## Status vocabulary

Used identically here, in `progress.md`, and on the dashboard.

| Status | Means |
|---|---|
| **Complete** | Written, reviewed, **and observed working** |
| **Built, unproven** | Written and reviewed, never run against real infrastructure |
| **Next** | The immediate next piece of work |
| **Planned** | Agreed, not started |
| **Retired** | Explored and superseded — kept, with the reason |

Do not mark something Complete because the code looks right. See
[`Main_App/testing.md`](Main_App/testing.md) for what "observed working" requires.

## Two deliberate exceptions

- **`CLAUDE.md` stays at the repo root.** It is loaded automatically from there by
  agent tooling; moving it into `docs/` would stop it being picked up.
- **The HTML files are standalone** — no server, no build. Open them from disk. The
  dashboard is hand-maintained: its story data lives in one `STORIES` object near
  the bottom of the file, and the cards, counts, and phase bars all follow from it.
