# Nora Home

The house operating system. A Django platform that runs on a Raspberry Pi 5 (8GB) and
hosts the apps our family builds: self-improvement, ambition, family health, Nora Robot
monitoring, house maintenance, and integrations.

**This repository is the skeleton.** It does not contain the family apps themselves — it
contains the platform that they plug into.

## What the skeleton gives a house app

| Capability | Where |
|---|---|
| App registry, nav, dashboard cards | `nora/core` |
| Household members, roles, contact endpoints | `nora/accounts` |
| Slack alerts + multi-channel notifications | `nora/notifications` |
| Trackables, schedules, completion + escalation | `nora/tracker` |
| AI via the Claude API | `nora/ai` |
| MCP server exposing house data to agents | `nora/mcpserver` |
| MySQL / MongoDB / Redis / object storage | `nora/datastores` |
| Backup, restore, migrate | `nora/datastores/management/commands` |
| Always-on display + 10.1" kiosk control bus | `nora/displays` |
| Nora bot, theming, responsive shell | `nora/ui` |
| Integration framework (Home Assistant, stocks…) | `nora/integrations` |
| Time-series telemetry (robot, health, sensors) | `nora/telemetry` |

## Quick start (development)

```bash
python -m venv .venv && . .venv/Scripts/activate   # Windows
pip install -r requirements/dev.txt
cp .env.example .env
python manage.py migrate
python manage.py bootstrap_home --demo
python manage.py runserver
```

Open http://localhost:8000/home/ — the dashboard, with the home bot zipping around.
Open http://localhost:8000/capabilities/ — the living capability sheet.

Infrastructure (MySQL, Mongo, Redis, RabbitMQ, MinIO) comes up with:

```bash
docker compose up -d
```

## Documents

- [`CLAUDE.md`](CLAUDE.md) — project state, progress log, decisions.
- [`DEVELOPMENT.md`](DEVELOPMENT.md) — **how to write an app for this system.** Point your
  AI agent at this file.
- [`docs/capabilities.html`](docs/capabilities.html) — what the platform can do today.
- [`docs/deployment-pi.md`](docs/deployment-pi.md) — Raspberry Pi 5 + dual display setup.
