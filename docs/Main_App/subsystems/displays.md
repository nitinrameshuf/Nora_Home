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
for your app. Declare `nora_wall_panels` for wall panels. See
[`../cross-functionality.md`](../cross-functionality.md#displays) and
[`../DEVELOPMENT.md`](../DEVELOPMENT.md).

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

## Known gaps

- **DPMS blanks both screens together**, not just the wall. Confirmed on hardware
  and accepted — per-output `xrandr --off` had already proven fragile.
- `Display.rotation_enabled` / `rotation_seconds` / `current_panel` still exist on
  the model but mean nothing now the wall mirrors a real page. They were removed
  from the Displays page UI, which was showing a stale panel key and a rotation
  interval nothing honoured. The fields were left in place rather than migrating
  them away.
- The old ambient wall (`wall.html`, `wall.js`) is kept, unused, in case a passive
  view is ever wanted again.

## Files

```
models.py      Display, DisplayCommand
bus.py         send_to_display, broadcast
consumers.py   DisplayConsumer (wall listens), KioskConsumer (kiosk sends)
views.py       wall, kiosk, manage, command
tasks.py       check_displays_online
```

Templates: `displays/wall_live.html` (current), `displays/kiosk.html`,
`displays/manage.html`, `displays/wall.html` (retired ambient view).
Scripts: `static/nora_home/js/wall-live.js`, `kiosk.js`, `wall.js` (retired).
