# Integrations — `nora_home.integrations`

## What it is

The framework for pulling the outside world in on a schedule: weather, Home
Assistant, markets, calendars. Scheduling, exponential backoff, failure alerting,
and credential handling are all provided — an integration implements `fetch()` and
nothing else.

## Status

**Complete as a framework, with one real integration.** Weather runs live on the
Pi against Open-Meteo.

## Models

| Model | Holds |
|---|---|
| `Integration` | provider, enabled, interval, last run, failure count, config |
| `IntegrationRun` | One attempt: started, duration, records, ok/failed, error |

## Writing one

Subclass the provider base, implement `fetch()`, return records. The framework
handles the rest.

```python
class WeatherProvider(BaseProvider):
    slug = "weather"
    description = "Outside temperature and condition, from Open-Meteo — no API key."

    def fetch(self):
        ...
        return {"condition": condition, "temp_c": temp_c}
```

**Credentials never go in the database.** `Integration.secret()` reads them from the
environment, so a database dump shared for debugging carries no tokens
([`../../CLAUDE.md`](../../../CLAUDE.md) § 4).

Repeated failure backs off and eventually notifies the house rather than retrying
forever in silence.

## Providers

| Provider | Status | Notes |
|---|---|---|
| `weather` | **Live** | Open-Meteo. No API key — just `NORA_HOME_LAT` / `NORA_HOME_LON`. Feeds the living background and the `weather.temperature_c` telemetry series |
| Home Assistant | Planned | Story 25. Entity states into telemetry, which puts them on the wall and in the MCP tools for free |

## What it offers other apps

Fires `core.signals.integration_synced` after a successful poll. Most integrations
should write their results through `telemetry.api.record_reading()` rather than
inventing a table — that is what makes them chartable and alertable with no extra
work.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `poll_due_integrations` | every 5 min | Runs any integration whose interval has elapsed |
| `run_integration` | on demand | One integration, with backoff and failure recording |

## Settings

| Key | For |
|---|---|
| `NORA_HOME_LAT` / `NORA_HOME_LON` | House location — drives weather **and** the season/daylight calculation for the living background |

Provider credentials are read per-integration from the environment, never stored.

## Known gaps

- Only one concrete integration exists.
- Home Assistant (Story 25) is the obvious next one and is unblocked.

## Files

```
models.py            Integration, IntegrationRun
providers/base.py    BaseProvider — implement fetch()
providers/weather.py Open-Meteo
tasks.py             poll_due_integrations, run_integration
views.py             index
```
