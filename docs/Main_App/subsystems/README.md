# docs/platform/

One file per subsystem of **the base app** — the platform itself. Apps the family
wrote live in [`../houseapps/`](../../House_Apps/).

Each of these is its own Django app under `nora_home/` for code organisation.
Nobody "installed" them the way a house app gets added, and they are not listed on
the Apps page for that reason — that page shows family apps only.

## The subsystems

| Doc | Module | What it owns | Status |
|---|---|---|---|
| [`core.md`](core.md) | `nora_home.core` | The app registry, base models, settings store, audit, health | Complete |
| [`accounts.md`](accounts.md) | `nora_home.accounts` | Who lives here, roles, escalation contacts, passwordless auth | Complete |
| ~~`tracker.md`~~ | ~~`nora_home.tracker`~~ | **Deleted 2026-08-06 (Story 40).** Todo absorbed it; see [`todo.md`](todo.md) | Retired |
| [`notifications.md`](notifications.md) | `nora_home.notifications` | Slack / in-app / wall / console delivery, receipts, retries | Built, unproven |
| [`telemetry.md`](telemetry.md) | `nora_home.telemetry` | Every number in the house, over time, with thresholds | Complete |
| [`displays.md`](displays.md) | `nora_home.displays` | The 24" wall, the 10.1" kiosk, and the bus between them | Complete |
| [`dashboard.md`](dashboard.md) | `nora_home.dashboard` | The home screen: widget registry and per-person layouts | Complete |
| [`integrations.md`](integrations.md) | `nora_home.integrations` | Pulling the outside world in on a schedule | Complete |
| [`ai.md`](ai.md) | `nora_home.ai` | Claude, model tiers, cost accounting, monthly budget | Built, unproven |
| [`datastores.md`](datastores.md) | `nora_home.datastores` | Mongo, object storage, backup and restore | Built, unproven |
| [`mcpserver.md`](mcpserver.md) | `nora_home.mcpserver` | The house as MCP tools, over stdio and HTTP | Built, unproven |
| [`ui.md`](ui.md) | `nora_home.ui` | Surfaces, the living background, the home bot | Complete |

Status uses the vocabulary in [`../README.md`](../../README.md) — *built, unproven*
means written and reviewed but never run against real infrastructure, which is the
honest state of anything needing an API key or a live third-party service.

## What to read instead, depending on the question

| Question | Go to |
|---|---|
| "How do I call this from my app?" | [`../cross-functionality.md`](../cross-functionality.md) — signatures and arguments |
| "How does the whole thing fit together?" | [`../architecture.md`](../architecture.md) — diagrams and data flow |
| "How do I build an app on top of it?" | [`../DEVELOPMENT.md`](../DEVELOPMENT.md) |
| "What does this one subsystem own?" | The files here |

These pages describe **what each subsystem is and owns**. They deliberately do not
repeat the call signatures — those live in one place, `cross-functionality.md`, so
there is only ever one copy to keep correct.

## Required sections

Same headings as a house app's README, so everything reads alike: *What it is*,
*Status*, *Models*, *What it offers other apps*, *Background work*, *Settings*,
*Known gaps*, *Files*.
