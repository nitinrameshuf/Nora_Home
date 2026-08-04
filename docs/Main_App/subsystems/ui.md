# UI — `nora_home.ui`

## What it is

The shell every page sits inside: surface detection, the living background, the
theme, and the home bot. It holds no database tables and no pages of its own
(`nora_has_page = False`) — it exists so the platform has one place to own how the
house *looks* on five different screens.

## Status

**Complete.** Verified on the physical wall and kiosk.

## Surfaces

`middleware.py` names the surface server-side and puts it on
`<html data-surface="...">`, so CSS and templates respond without measuring
viewports in JavaScript.

| Surface | Device | Detected by |
|---|---|---|
| `wall` | 24" 1080p, HDMI-0, always on | URL |
| `kiosk` | 10.1" 1024×600 touchscreen, HDMI-1 | URL |
| `phone` | iPhone / Android | User-Agent |
| `tablet` | iPad | User-Agent |
| `desktop` | laptop / monitor | fallback |

`request.nh_surface` and `request.nh_is_touch` are available in every view; an
`nh_surface` cookie overrides detection for testing. Full guidance in
[`../DEVELOPMENT.md`](../DEVELOPMENT.md) § The five surfaces.

## The living background — "Almanac"

The design language: the **real** season, time of day, and outside weather are
composited as a living background *behind* the fully-functional app. Never
replacing it, never becoming an ambient screen — both of those were explicitly
tried and rejected.

> *"Charm outside, polish inside."* The atmosphere (sky gradient, horizon,
> sun/moon, rain/snow/clouds) carries the personality; the data on top, in
> translucent glass panes, stays disciplined — tabular numbers, no ornamentation.

| Piece | Where |
|---|---|
| Season from date + house latitude; day/night from **real** sunrise/sunset | `scene.py` |
| Sky, orb, horizon, precipitation, glass panes | `static/nora_home/css/nh-scene.css` |
| Polling so long-open screens don't drift | `static/nora_home/js/nh-scene.js` |

Both screens poll `core:weather_current` every 5 minutes so they cannot end up
showing different "moments".

**Legibility is solved with text colour, not opacity.** Two earlier attempts raised
the glass panes' opacity — flat, then daypart-scaled — and both were reverted:
raising opacity to fix contrast just hides the thing the design exists to show.
Opacity stays low and fixed; `--text` / `--text-dim` / `--text-faint` switch by
theme instead. Do not "fix" contrast by making the panes more opaque.

## The home bot

A small CSS rover that drives along the **bottom strip** of the screen, left and
right only — `moveTo()` takes no vertical position at all, so it can never wander
up into the content. Clicking it says "Hi"; what it should really do is open.

`ui/bot.py` and `ui/consumers.py` carry the websocket: server → browser for things
to say, browser → server for interaction beats. `data-nh-bot="off"` on `<html>`
disables it (the wall and kiosk both do).

> `nh-bot.js` must **extend** `window.NoraHome`, never assign it. It used to end
> with `window.NoraHome = NoraHome`, which wiped `csrfToken()` and `post()` that
> `nh-app.js` had already put there — silently breaking the widget picker's save,
> which 403'd and then reloaded as though it had worked.

## What it offers other apps

Surface detection on every request, the house CSS, and
`NoraHome.say(message, {mood})` from JavaScript. `POST /api/homebot/say/` is how the
robot puts a line on the house screens.

## Background work

None.

## Settings

| Key | For |
|---|---|
| `NORA_HOME_LAT` / `NORA_HOME_LON` | Season and real sunrise/sunset for the scene |

## Known gaps

- **Continuous motion over hours is unverified.** The scene was checked for
  minutes, not hours; whether rain/snow/stars plus backdrop blur on every pane
  holds up on a Pi 5 driving two Chromium instances all day is still unknown.
- A full type scale and per-component restyle across all five surfaces was never
  done — only `.card`, `.sidebar`, `.kiosk-tile` and later `.dash-tile` were
  retrofitted onto the glass material.
- No tests (Story 21).

## Files

```
middleware.py         SurfaceMiddleware
scene.py              season, daypart from real sunrise/sunset
context_processors.py scene + house name into every template
bot.py                the bot's server side
consumers.py          the homebot websocket
```

Front end: `nh-scene.css`, `nh-scene.js`, `nh-bot.css`, `nh-bot.js`,
`nora-home.css`, `nh-app.js`.
