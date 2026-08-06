# Displays — `nora_home.displays`

## What it is

The two physical screens the Pi drives, and the websocket bus between them.

- **24" 1080p on HDMI-0** — always on, wall-mounted, read from ~3 metres. No touch,
  no mouse. It shows the **real app** inside a full-viewport iframe.
- **10.1" 1024×600 touchscreen on HDMI-1** — the **remote control**. It never shows
  app pages itself; it is a grid of big buttons. Tapping one sends the wall to that
  page and swaps the kiosk to that app's own controls.

## Status

**Complete.** Both screens verified on real hardware in Chromium kiosk mode,
including simulated touch confirming the kiosk drives the wall and the back button
returns without disturbing it.

## Models

| Model | Holds |
|---|---|
| `Display` | slug, kind (`wall` / `kiosk` / `ambient`), heartbeat, night-mode window |
| `DisplayCommand` | An audit trail of what was sent to which screen, by whom |

`Display.is_online` is derived from `last_seen_at` against a 90-second grace. Both
consumers register their row and heartbeat every 30s.

## The bus

`nora_home.displays.bus` — `send_to_display(slug, payload)`, `broadcast(payload)`.
Channels group per display, so a message reaches every browser showing that screen.

**Message types the wall actually implements** (`static/nora_home/js/wall-live.js`):

| `type` | Effect |
|---|---|
| `navigate` | Point the iframe at `path` |
| `refresh` | Reload the wall page |
| `banner` | Alert takes over the top of the wall, then hands it back |

The bus relays anything; the browser ignores what it has no handler for. **Adding a
message type means adding its handler in the same commit** — otherwise you ship a
control that looks wired up and does nothing. This has bitten twice: the kiosk's
Dim/Wake buttons, and the notification banner. Both fixed 2026-08-03.

`KIOSK_ACTIONS` in `consumers.py` is the allow-list of what the kiosk may send, and
is deliberately kept to exactly what the wall implements.

## What it offers other apps

Declare `nora_kiosk_controls` in your `apps.py` and the kiosk grows a button screen
for your app. See [`../cross-functionality.md`](../cross-functionality.md#displays)
and [`../DEVELOPMENT.md`](../DEVELOPMENT.md).

`nora_wall_panels` and its rotation mechanism were removed 2026-08-05 (Story 28)
— dead code since the wall was repointed at the live app; nothing had rendered a
wall panel since. The 24" now shows the real app, and what an app puts there is
whatever it renders at its own URL — see
[`subsystems/todo.md`](todo.md) §6 for how Todo does this.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `check_displays_online` | periodic | Notifies the house if the always-on wall stops heartbeating for 10+ minutes |

`rotate_wall_display` was removed 2026-08-03. It fired every 45 seconds to advance
the old ambient wall's panel rotation, which the iframe wall ignores entirely — it
was waking the worker forever to send a message nothing listened for.

## Settings

| Key | For |
|---|---|
| `NORA_HOME_MAIN_DISPLAY_SLUG` | Which display is "the wall" (`wall`) |
| `NORA_HOME_KIOSK_DISPLAY_SLUG` | Which is the kiosk (`kiosk`) |

Screen power is a **host-side** concern, not this app's: a schedule in Settings is
applied by `~/.nora/wall-power.sh` via `xset dpms` on a systemd timer, because
Django runs in Docker and the monitors are on the Pi's own X session.

## Where it appears

No nav entry (`nora_nav = False`). The two screens' status cards live on the
**Settings** page, directly above the wall power schedule that configures them;
`/home/displays/` redirects there. `/home/displays/wall/` and
`/home/displays/kiosk/` are unaffected — they are what the physical screens load.

## Known gaps

- **Nothing served from this app can touch the physical Chromium windows.** Django
  runs in Docker with no `DISPLAY`, no X socket mount, and no host networking, so
  there is no way to minimize, close, move, or focus the wall/kiosk windows from a
  web page. The only bridge that exists is host-side and polls: `~/.nora/wall-power.sh`
  runs `manage.py wall_power_state` on a 5-minute systemd timer and acts with
  `xset`. Any window control would need the same shape — a host agent polling for
  intent — with a much shorter interval to feel like a button.
- **DPMS blanks both screens together**, not just the wall. Confirmed on hardware
  and accepted — per-output `xrandr --off` had already proven fragile.
- ~~`Display.rotation_enabled` / `rotation_seconds` / `current_panel` still exist~~
  **Removed 2026-08-04** (migration `0002`), along with `pinned_until`,
  `night_mode_start`/`_end`, and `brightness`. Leaving them "in case a passive
  view is wanted again" turned out to be the trap, not the safety net: they kept
  admin columns and a websocket connect payload alive that reported values
  nothing set and `wall-live.js` had never read. The old ambient wall
  (`wall.html`, `wall.js`) went with them — nothing rendered either file. Git
  history is the archive if a passive view is ever wanted.

## Files

```
models.py      Display, DisplayCommand
bus.py         send_to_display, broadcast
consumers.py   DisplayConsumer (wall listens), KioskConsumer (kiosk sends)
views.py       wall, kiosk, command (manage now redirects to core:settings)
tasks.py       check_displays_online
```

`command` is mounted at `command/<slug>/`, not `<slug>/command/`: the latter is
ambiguous with `wall/<slug>/` and Django resolves in order, so
`/home/displays/wall/command/` matched `wall_named(slug="command")` and the
endpoint was unreachable for the one display the kiosk targets.

Templates: `displays/wall_live.html` (current) and `displays/kiosk.html`. The
screen cards live in `core/settings.html`.
Scripts: `static/nora_home/js/wall-live.js` and `kiosk.js`.
