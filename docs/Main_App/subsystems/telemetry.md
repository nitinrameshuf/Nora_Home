# Telemetry — `nora_home.telemetry`

## What it is

One time-series store for **every number in the house**. Weight, sleep, HRV, room
temperature, the robot's battery, litres of water, a portfolio value — they are all
"a named number, measured at a time, optionally about a person".

Record here instead of adding a column and you get history, charts, rollups,
retention, and threshold alerts for free — and the number appears in *House vitals*
alongside every other app's.

## Status

**Complete.** Observed working on the Pi: the weather integration writes
`weather.temperature_c` every few minutes, and it renders in the House vitals
widget on the wall.

## Models

| Model | Holds |
|---|---|
| `Series` | The definition: key, label, unit, owner, direction, thresholds, precision, retention |
| `Reading` | One measurement: value, when, who, source, free-form tags |
| `HourlyRollup` | Compacted history, so two years of data does not mean two years of rows |

Two tables on purpose — the definition rarely changes, the data table is hot, and
keeping it narrow matters on a Pi.

Keys are dotted and namespaced: `body.weight`, `house.living_room.temp`,
`nora.battery`, `money.portfolio`.

## Thresholds

`warn_below` / `warn_above` / `alert_below` / `alert_above` on the series turn a
number into an alert. Crossing one fires `core.signals.threshold_crossed` **and**
notifies — the recording app wires up nothing.

`direction` (`up`, `down`, `range`, `neutral`) is what lets a widget colour a delta
correctly without knowing what the number means.

## What it offers other apps

`nora_home.telemetry.api` — `define_series()`, `record_reading()`,
`series_history()`. Signatures in
[`../cross-functionality.md`](../cross-functionality.md#telemetry).

`HouseVitalsWidget` deliberately queries every active series with **no `app_slug`
filter**, so any app that records a reading appears there automatically with
nothing to register. Provides MCP tools.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `rollup_hourly` | hourly, :07 | Compacts raw readings into `HourlyRollup` |
| `prune_readings` | periodic | Drops raw readings past the series' `retention_days` (default 730) |

## Settings

None of its own. Per-series behaviour is data, not config.

## Known gaps

- **Only one series exists in this house** — `weather.temperature_c`, from the
  weather integration. Nothing else has ever written to it, and that number is
  already visible in House vitals and in the living background, so the Measurements
  page currently shows one number a second time. It is real infrastructure waiting
  for a real app; worth revisiting whether it should be in the nav until then.
- `record_reading()` auto-creates a series when the key is unknown, which is
  convenient for prototyping and a trap in production: you get no unit, no
  thresholds, and a guessed label. Call `define_series()` once.

## Files

```
models.py    Series, Reading, HourlyRollup
api.py       define_series(), record_reading(), series_history()
widgets.py   HouseVitalsWidget
tasks.py     rollup, prune
views.py     index, detail, history JSON, manual record
```
