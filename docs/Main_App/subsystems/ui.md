# UI — `nora_home.ui`

## What it is

The shell every page sits inside: surface detection, the living background, the
theme, and the home bot. It holds no database tables and no pages of its own
(`nora_has_page = False`) — it exists so the platform has one place to own how the
house *looks* on five different screens.

## Status

**Complete.** Deployed to the Pi and screenshotted, 943 tests green.

The stylesheet is **compiled, not hand-written**: `assets/css/nora.css` →
`static/nora_home/css/nh.css`, built by the Dockerfile's `css` stage with
Tailwind v4. Node lives in that stage only. `nh.css` is gitignored and linked
last in `base.html`, **after `{% block head %}`** — per-page sheets are injected
into that block, so anything linked above it loads earlier and loses.

Type is six fluid `clamp()` roles covering phone through 4K. The 24" is an
ordinary monitor and has no type scale of its own; `nora_home/ui/zoom.py` and
Settings → Screens serve the 10.1" kiosk alone. Surface detection still exists
and still drives the kiosk's touch sizing, but no longer selects a type scale.

The living background is hidden in the app chrome. `scene.py`, `nh-scene.css`
and the Open-Meteo integration all still work and are still wired — the target
is the kiosk's idle screen. Nothing in an app should reference them.

## Surfaces

`middleware.py` names the surface server-side and puts it on
`<html data-surface="...">`, so CSS and templates respond without measuring
viewports in JavaScript.

| Surface | Device | Detected by |
|---|---|---|
| `wall` | 24" 1080p, HDMI-0, always on | URL, or an iframe of it — see below |
| `kiosk` | 10.1" 1024×600 touchscreen, HDMI-1 | URL |
| `phone` | iPhone / Android | User-Agent |
| `tablet` | iPad | User-Agent |
| `desktop` | laptop / monitor | fallback |

`request.nh_surface` and `request.nh_is_touch` are available in every view; an
`nh_surface` cookie overrides detection for testing. Full guidance in
[`../DEVELOPMENT.md`](../DEVELOPMENT.md) § The five surfaces.

### The wall's iframe

"URL" covers the wall's *shell* page only. The shell is a bare frame around an
iframe of the real app (see [`displays.md`](displays.md)), and the app inside is
requested at its own ordinary URL — `/home/`, `/todo/` — with no "wall" in the
path at all. Two signals promote those requests:

| Signal | Covers |
|---|---|
| `Sec-Fetch-Dest: iframe` + a referer naming the wall's shell | the first hop, when the kiosk points the wall somewhere |
| `Sec-Fetch-Dest: iframe` + **any same-origin** referer | every hop after that |

The second was missing until 2026-08-07 and its absence was invisible: only
the first hop carries the shell as its referer, so **clicking a link on the
24" itself dropped the wall surface** — laptop type scale, wall zoom gone,
nothing logged. It only showed up because the mouse pointer, which the wall
hides and a laptop does not, started behaving differently depending on how the
page had been reached.

Same-origin is the boundary because a page on another origin embedding the
house either sends no `Referer` or sends its own, and fails the host check
either way. What it does assume is that **nothing in this house iframes an app
page except the wall** — true today, and the thing to check before adding a
second iframe anywhere.

Still stateless — no cookie — so someone opening the app on their own laptop
can never get stuck wall-sized.

### The wall's mouse pointer

The wall hides its pointer **only while the mouse is still** (4s), via
`data-cursor="idle"` on `<html>`, set by `wireWallCursor()` in `nh-app.js` and
acted on in `nora-home.css`. It hid the pointer outright until 2026-08-07,
which dated from when the wall was a passive ambient view; it is the real app
now and gets driven from its own sidebar, so a permanently invisible pointer
means aiming blind.

The CSS is `body, body *` rather than just `body` on purpose: `cursor` is
inherited, and an inherited value loses to any directly-declared one —
including the browser's own `a:link { cursor: pointer }`. That is why the old
rule hid the pointer over the page body and let it reappear over every link,
which reads as a rendering fault rather than as a choice.

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
