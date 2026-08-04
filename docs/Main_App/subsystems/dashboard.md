# Dashboard — `nora_home.dashboard`

## What it is

The home screen: a 12-column grid each person arranges for themselves, built from
widgets that **any** app offers. Apps offer visualizations; they never decide where
they go.

## Status

**Complete.** Verified on hardware — the picker adds and removes tiles, layouts
persist per person, and the grid renders on the wall.

## Models

| Model | Holds |
|---|---|
| `DashboardLayout` | One person's arrangement: which widgets, at what x/y/w/h |

`DashboardLayout.Surface` distinguishes a personal layout from `SHARED` — the
"Everyone" view.

## Widgets return data, not HTML

This is the rule that keeps every chart in the house looking like one system no
matter who wrote the app. A `ChartWidget` returns an **ECharts option dict** and the
platform applies the house theme.

| Base class | Implement | Returns |
|---|---|---|
| `ChartWidget` | `option(request)` | ECharts option dict |
| `StatWidget` | `stat(request)` | value, unit, label, delta, status, sparkline |
| `ListWidget` | `rows(request)` | title, meta, status, url, action_url |
| `TemplateWidget` | `context(request)` | Context for your own template — the escape hatch |

Full usage in [`../cross-functionality.md`](../cross-functionality.md#dashboard-widgets).

## No build step, on purpose

**ECharts and Gridstack are vendored** into `static/nora_home/vendor/` rather than
pulled from a CDN, because the house must work with the internet down. There is
deliberately **no npm, no bundler, and no framework** — a family member's agent
should be able to add a chart without a toolchain, and the Pi should never run a
build.

The dashboard is useful with **neither** library present: without Gridstack the
grid is static but correct, and without ECharts chart tiles show a short note.

## What it offers other apps

The widget base classes, and `registry.all_widgets(role)`. Declare
`nora_widgets = [...]` in your `apps.py` and your widget appears in everyone's
picker.

## Background work

None.

## Settings

None of its own.

## Known gaps

- No tests (Story 21).
- Two real layout bugs were found only by measuring rendered pixels, both fixed and
  worth not reintroducing:
  - `.dash-tile { height: 100% }` fought Gridstack's own `inset`-based sizing.
    Setting `top`, `bottom` **and** `height` over-constrains the box, so the browser
    drops Gridstack's bottom inset and the tile ends up exactly one margin too tall,
    silently erasing the vertical gap. It is now scoped to the static fallback only.
  - `.dash-tile` is built by `dashboard.js`, not a template, so it never carried
    `class="card"` and never picked up the living background's glass material — it
    sat on a flat opaque background for as long as that background existed.
- Gridstack injects its CSS via `insertRule`, so `<style>.textContent` is **empty**.
  Walk `document.styleSheets[i].cssRules` to inspect it.

## Files

```
models.py    DashboardLayout
widgets.py   Widget, ChartWidget, StatWidget, ListWidget, TemplateWidget
views.py     home, catalog, save_layout, widget_data
```

Front end: `static/nora_home/js/dashboard.js`, `nh-charts.js`,
`static/nora_home/css/dashboard.css`.
