# Architecture

How Nora Home is put together, and why. Diagrams are Mermaid — GitHub, VS Code, and
most Markdown viewers render them inline.

> **Nora Home is not Nora.** Nora is the family's robot, a separate machine with its
> own repository. Nora Home is the house system it lives alongside. They meet at
> exactly two places, both listed under [Boundaries](#boundaries).

---

## 1. The shape of the thing

Nora Home is a **platform**, not an application. The base system provides plumbing;
the apps the family writes provide the value. Everything below the dashed line is
what a house app gets for free.

```mermaid
graph TB
    subgraph HouseApps["houseapps/ — what the family writes"]
        W[workout]
        F[family]
        M[maintenance]
        R[robot monitor]
    end

    REG{{"nora_home.core.registry<br/>NoraAppConfig"}}

    subgraph Platform["nora_home/ — the platform"]
        TRK[tracker<br/>schedules · escalation]
        NOT[notifications<br/>slack · display · in-app]
        DASH[dashboard<br/>widgets · layouts]
        TEL[telemetry<br/>time series · thresholds]
        AI[ai<br/>Claude · budget]
        MCP[mcpserver<br/>tools for agents]
        DS[datastores<br/>mongo · objects · backup]
        DISP[displays<br/>wall · kiosk bus]
        INT[integrations<br/>polling framework]
        UI[ui<br/>surfaces · home bot]
    end

    W --> REG
    F --> REG
    M --> REG
    R --> REG
    REG -.->|"URL mount · nav · widgets<br/>wall panels · MCP listing"| Platform

    classDef app fill:#1e3a5f,stroke:#3b82f6,color:#dbeafe
    classDef plat fill:#1e293b,stroke:#475569,color:#e2e8f0
    classDef reg fill:#3b0764,stroke:#a855f7,color:#e9d5ff
    class W,F,M,R app
    class TRK,NOT,DASH,TEL,AI,MCP,DS,DISP,INT,UI plat
    class REG reg
```

**The contract is one class.** A house app subclasses `NoraAppConfig` in its
`apps.py` and declares a slug, a category, and which widgets and wall panels it
offers. From that the platform derives its URL, its nav entry, its place on the home
screen and the wall, and its presence in the MCP tool listing. Nothing else is wired
by hand — `config/urls.py` is never edited to add an app.

---

## 2. Processes and data stores

```mermaid
graph LR
    subgraph Pi["Raspberry Pi 5 · 8GB · Docker Compose"]
        WEB["web<br/>Daphne ASGI<br/>:8000"]
        WORK["worker<br/>Celery"]
        BEAT["beat<br/>Celery scheduler"]

        MYSQL[("MySQL<br/>relational core")]
        MONGO[("MongoDB<br/>documents")]
        REDIS[("Redis<br/>cache · channels")]
        RABBIT[["RabbitMQ<br/>work queues"]]
        MINIO[("MinIO<br/>object storage")]
    end

    WALL["24&quot; wall display<br/>HDMI-0 · Chromium kiosk"]
    KIOSK["10.1&quot; kiosk<br/>HDMI-1 · Chromium kiosk"]
    PHONE["phones · iPads · laptops"]

    WALL <-->|websocket| WEB
    KIOSK <-->|websocket| WEB
    PHONE <-->|https| WEB

    WEB --> MYSQL
    WEB --> MONGO
    WEB --> REDIS
    WEB --> MINIO
    WEB -->|enqueue| RABBIT

    RABBIT --> WORK
    BEAT -->|schedule| RABBIT
    WORK --> MYSQL
    WORK --> MONGO
    WORK --> MINIO
    WORK -->|results| MYSQL

    SLACK([Slack])
    CLAUDE([Claude API])
    WORK --> SLACK
    WORK --> CLAUDE
```

### Why each store

| Store | Holds | Chosen because |
|---|---|---|
| **MySQL** | Members, trackables, occurrences, notifications, telemetry, layouts | Anything the tracker or escalation engine joins across. Relational, transactional, migratable. |
| **MongoDB** | Journals, AI transcripts, raw integration payloads, sensor bursts | Shapes that change as ideas change, without a migration each time. **Optional** — the house runs degraded, not broken, without it. |
| **Redis** | Cache, Channels layer, rate limits | Fast, ephemeral, and already needed for websockets. |
| **RabbitMQ** | Celery work queues | Durable queues and real routing, so a runaway app task cannot delay an escalation. Collapsible to Redis on a laptop via `NORA_HOME_BROKER_USE_REDIS=1`. |
| **MinIO** | Photos, exports, backups, robot recordings | S3-compatible and runs on the Pi. Falls back to local disk when `NORA_HOME_S3_ENABLED=0`. |

### Queue separation

Five queues, so one app's slowness is never another's outage:

| Queue | Carries | Who may use it |
|---|---|---|
| `platform` | Health snapshots, rollups, display rotation, backups | Platform only |
| `alerts` | Notification delivery, escalation sweeps | Platform only |
| `apps` | Everything a house app schedules | **House apps — use this** |
| `ai` | Claude calls | Anyone |
| `integrations` | Outside-world polling | Integration framework |

---

## 3. The tracker and the escalation ladder

The spine of the system, and the reason it is not a todo list.

```mermaid
graph TD
    T["Trackable<br/><i>the standing intent</i><br/>'change the filter quarterly'"]
    O["Occurrence<br/><i>one concrete due instance</i><br/>materialized 2 weeks ahead"]
    C["Completion<br/><i>evidence</i><br/>who · when · note · photo"]
    E["EscalationEvent<br/><i>immutable record</i><br/>that the house pushed harder"]

    T -->|"materialize()"| O
    O -->|"complete()"| C
    O -->|"overdue + policy"| E

    P["EscalationPolicy<br/><i>editable JSON ladder</i>"]
    P -.-> E
```

Three layers, kept separate on purpose:

- **Trackable** — the standing intent. Belongs to a person and to an app.
- **Occurrence** — one concrete due instance. **Written ahead of time, not computed
  on read.** That is what makes "what did I miss last March" answerable and gives
  escalation state somewhere to live.
- **Completion** — evidence, kept separately so history survives an occurrence being
  reopened.

### The ladder

```mermaid
sequenceDiagram
    participant O as Occurrence
    participant E as Escalation engine
    participant M as Owner
    participant C as Their chain
    participant H as Whole house

    Note over O: due_at passes
    E->>O: sweep every 5 min
    E->>M: L1 nudge (after grace)
    Note over M: still not done
    E->>M: L2 warning (+2h)
    Note over M: still not done
    E->>C: L3 alert (+12h)
    Note over C: still not done
    E->>H: L4 critical (+48h) · Slack + wall display
    Note over O: acknowledge() at any point stops the climb
```

`EscalationPolicy.levels` is JSON, so the ladder is editable in the admin without a
deploy. Three ship by default: **House default**, **Gentle** (for habits), and
**Safety critical** (medication, alarms — 15 minutes to all adults).

---

## 4. Notifications

Intent and delivery are separate records. That is what makes "did anyone actually
see this?" answerable.

```mermaid
graph LR
    API["notify() / notify_house()"]
    N["Notification<br/><i>the intent</i>"]
    D1["Delivery: slack"]
    D2["Delivery: display"]
    D3["Delivery: inapp"]

    API --> N
    N --> D1 & D2 & D3

    D1 --> SL([Slack DM or channel])
    D2 --> WD([wall display banner])
    D3 --> IA([bell + live push])

    Q{{"quiet hours<br/>severity ≥ alert overrides"}}
    API -.-> Q
```

Each `Delivery` records attempts, errors, timestamps, and the provider's own
reference. Failures retry on a sweep; permanent ones stay recorded rather than
disappearing.

---

## 5. The two screens

The Pi drives both HDMI outputs. The 24" wall shows the real app — the same
`/home/` a phone or laptop would render, inside a thin iframe shell
(`displays/wall_live.html`) — full-size, for anyone in the room to read, but
with no touch or mouse of its own. The 10.1" kiosk is its **remote
control**: a fixed grid of buttons, never the app itself. Commands travel
through the server (Channels + Redis), not directly between the two screens.

```mermaid
sequenceDiagram
    participant K as Kiosk 10.1"
    participant S as Server (Channels + Redis)
    participant W as Wall 24"

    K->>S: {action: "navigate", path: "/workout/log/"}
    S->>W: display.message {type: "navigate", path}
    W->>W: iframe.src = path

    W->>S: heartbeat (30s)
    Note over S: no heartbeat for 10 min → notify the house
```

Every registered house app gets one kiosk button for free, switching the
wall to that app's front page. An app that declares
`nora_kiosk_controls` on its `NoraAppConfig` (see `DEVELOPMENT.md`) gets a
whole extra button screen on the kiosk — tapping any of its buttons still
just sends a `navigate` command, to that app's own page instead of its
front page. The wall's outer page and its websocket never reload on
navigation, only the iframe's `src` changes, so a burst of kiosk taps
doesn't cost a reconnect each time. If the socket dies, commands fall back
to a plain HTTP POST (`displays/command/`) so the kiosk still works.

A `Settings` page (`core:settings`, in the URL map below) holds house-wide
configuration — `HouseSetting`, a generic cached key/value store that
already existed but had no UI reading or writing it until now. First
setting: a schedule for when the wall display powers off. Django decides
on/off (`manage.py wall_power_state`, timezone-aware); a small host-side
script and systemd timer — outside Docker, since that's where the actual
X11 session and monitor live — poll it every 5 minutes and act with
`xset dpms force`.

---

## 6. The home screen

Each person arranges their own grid from widgets any app offers.

```mermaid
graph LR
    subgraph Apps
        A1["workout.WeeklyVolume<br/>ChartWidget"]
        A2["tracker.TodayWidget<br/>ListWidget"]
        A3["core.HouseHealthWidget<br/>StatWidget"]
    end

    CAT["all_widgets()<br/><i>the menu</i>"]
    LAY[("DashboardLayout<br/>per member<br/>x · y · w · h")]
    GRID["12-column grid<br/>Gridstack + ECharts"]

    A1 & A2 & A3 --> CAT
    CAT --> GRID
    LAY --> GRID
```

**Widgets return data, not HTML.** `ChartWidget.option()` returns an ECharts option
dict; the platform applies colour, type, and dark/light. That is what keeps a chart
written by one family member looking like a chart written by another.

Both libraries are **vendored into the repo**. The house must render with the
internet down, and the Pi must never run a build step.

---

## 7. Request path

```mermaid
graph LR
    REQ([request]) --> SEC[SecurityMiddleware]
    SEC --> WN[WhiteNoise]
    WN --> SESS[Session + Auth]
    SESS --> RC["RequestContextMiddleware<br/><i>request id · member</i>"]
    RC --> SURF["SurfaceMiddleware<br/><i>wall · kiosk · phone · tablet · desktop</i>"]
    SURF --> V[view]
    V --> RESP([response])
```

`SurfaceMiddleware` names the surface server-side and stamps it on `<html>`, so CSS
responds without any viewport measuring in JavaScript. The wall gets three-metre
type and the kiosk gets thumb-sized targets from the same stylesheet.

---

## 8. Boundaries

Rules that keep the system able to lose a part without losing the whole.

| Boundary | Rule |
|---|---|
| **App ↔ app** | Never import another app's models. Use `nora_home.tracker.api`, `nora_home.notifications.api`, `nora_home.telemetry.api`, or a signal from `nora_home.core.signals`. |
| **App ↔ environment** | No app reads `os.environ`. Settings go in `config/settings/base.py` with a default. |
| **Secrets ↔ database** | Credentials live in `.env` only. A database dump shared for debugging carries no tokens. |
| **Failure ↔ blast radius** | A card that raises renders "unavailable". A broken house app is skipped at mount. A dead Mongo is *degraded*, not *down*. The wall display survives everything. |
| **Nora Home ↔ Nora (robot)** | Two touchpoints only: the robot may post to `/api/homebot/say/` to put a line on the house screens, and it may read the MCP tools with a scoped device token. Nothing else is shared. |

---

## 9. Layout on disk

```
config/                 Django project — settings/, celery, urls, asgi, wsgi
nora_home/              THE PLATFORM
  core/                 registry, base models, cards, health, audit, logging, API
  dashboard/            widget base classes, per-member layouts
  accounts/             HouseMember (AUTH_USER_MODEL), roles, escalation contacts
  notifications/        channels, delivery receipts
  tracker/              trackables, occurrences, scheduling, escalation engine
  ai/                   Claude client, model tiers, cost accounting
  mcpserver/            MCP tool registry, stdio server, HTTP transport
  datastores/           mongo, object storage, backup/restore
  displays/             wall + kiosk models, bus, consumers
  telemetry/            series, readings, rollups, thresholds
  integrations/         polling framework
  ui/                   surface detection, home bot, theme
houseapps/              WHAT THE FAMILY WRITES (example_habit is the reference)
templates/              platform templates
static/nora_home/       css, js, vendor
docker/ scripts/ docs/  entrypoint, provisioning, this folder
```

---

## 10. URL map

```
/                       → redirects to /home/
/home/                  the home dashboard (per-person widget grid)
/home/tracker/          the tracker
/home/alerts/           notifications
/home/displays/         wall + kiosk management
/home/displays/wall/    THE 24" SCREEN — iframe shell, shows real app pages remotely
/home/displays/kiosk/   THE 10.1" SCREEN — button remote, never the app itself
/home/ai/               assistant console
/home/measurements/     telemetry
/home/integrations/     integrations
/home/apps/             app directory
/home/system/           health and audit
/home/settings/         house-wide configuration (HouseSetting-backed)
/home/capabilities/     the capability sheet
/accounts/              switch (passwordless), profile, household
/api/                   platform API (device-token auth)
/mcp/                   MCP tools over HTTP
/admin/                 Django admin

/<app-slug>/            EVERY HOUSE APP — /habits/, /workout/, /family/ …
```

House apps mount at the root so each reads like its own site.
`RESERVED_SLUGS` in `nora_home/core/registry.py` stops an app claiming a platform
prefix.
