# testing.md — how to actually verify a change

**For AI agents working on this repo.** The Pi is reachable from the machine this
repo is checked out on. Use it. This project's whole status vocabulary turns on the
difference between *"the code looks right"* and *"I watched it work"* — see
[`../CLAUDE.md`](../../CLAUDE.md) § 0. Nearly every real bug in `progress.md` was found
by running the thing, not by reading it.

---

## Access

```bash
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253      # the Pi
cd ~/Nora_Home                                      # the checkout, on the Pi
```

| | |
|---|---|
| Host | `192.168.1.253` (LAN only) |
| User | `ckstation` |
| Key | `~/.ssh/nora_pi` on the dev machine |
| Repo on the Pi | `~/Nora_Home` |
| App | `https://192.168.1.253/` — self-signed cert, so pass `-k` / `ignore_https_errors` |
| Sudo | passwordless (`scripts/pre-install-pi.sh` installed a validated NOPASSWD entry) |
| App login | none — passwordless by design; tap a name at `/accounts/switch/` |

**On these being written down.** There is no secret here: a private RFC1918 address,
a username, and the *path* to a key that lives on the dev machine. The key itself is
not in this repo and must never be. This is recorded deliberately so an agent can
verify its own work without asking, and **it does not need flagging every time it is
used** — using it as documented is the expected workflow, not something to check in
about.

---

## The deploy loop

Docs-only changes need no rebuild — `git pull` on the Pi is enough. Anything under
`nora_home/`, `templates/`, `static/`, or `config/` needs the rebuild, because
static files are collected into the image.

```bash
# on the dev machine
git add -A && git commit -m "..." && git push origin main

# on the Pi
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 \
  "cd ~/Nora_Home && git pull --ff-only && \
   docker compose build web && docker compose up -d --force-recreate web"

sleep 8   # give the entrypoint time to migrate and boot Daphne
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 \
  "cd ~/Nora_Home && docker compose ps web && docker compose exec -T web python manage.py check"
```

> **Never hot-copy a file into the container to "test quickly".** Django serves
> content-hashed static filenames (`nh-scene.2c282e12.css`). Editing the unhashed
> file inside the container changes nothing the browser will ever request, and you
> will spend an hour debugging a fix that did deploy. Only a real `collectstatic`
> — i.e. a real image build — updates what is served. This cost a session once.

---

## Checking from the outside: Playwright

Installed in the dev machine's `.venv`. This is the fastest way to see a page,
measure real pixels, or read computed CSS.

```python
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch()
    ctx = browser.new_context(ignore_https_errors=True,      # self-signed cert
                              viewport={"width": 1400, "height": 900})
    page = ctx.new_page()

    # Passwordless login: the first form button on the switcher is a house member.
    page.goto("https://192.168.1.253/accounts/switch/", wait_until="networkidle")
    page.click("form button[type=submit]")
    page.wait_for_load_state("networkidle")

    page.goto("https://192.168.1.253/home/", wait_until="networkidle")
    page.screenshot(path="/tmp/home.png", full_page=True)
    browser.close()
```

Useful variations:

| Need | How |
|---|---|
| Retina / hi-DPI check | `new_context(device_scale_factor=2)` — a fix can look fine at 1x and bad at 2x |
| Zoom into one element | `page.screenshot(clip=el.bounding_box())`, with `device_scale_factor=4` |
| Read computed CSS | `page.eval_on_selector_all(sel, "els => els.map(e => getComputedStyle(e).color)")` |
| Force a scene state | `page.evaluate("document.documentElement.setAttribute('data-daypart','noon')")` |
| Inspect JS-injected CSS | walk `document.styleSheets[i].cssRules` — Gridstack adds rules via `insertRule`, so `<style>.textContent` is **empty** |
| Check a global survived | `page.evaluate("typeof window.NoraHome.csrfToken")` |

**WebKit cannot reach this Pi.** Playwright's WebKit build defers to the OS for
certificate validation, so `ignore_https_errors` does not get it past the
self-signed cert. Test Safari-specific behaviour against a local file instead.

---

## Checking the real hardware

Playwright renders in a headless browser on the dev machine. It cannot tell you what
the 24" wall and the 10.1" kiosk are *actually showing* — for that, screenshot the
Pi's own X session.

```bash
# both physical screens, as one image
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 "DISPLAY=:0 scrot -o /tmp/screens.png"
scp -i ~/.ssh/nora_pi ckstation@192.168.1.253:/tmp/screens.png /tmp/screens.png
```

The two Chromium instances are launched by scripts `install-pi.sh` generated:

```bash
~/.nora/start-wall.sh     # HDMI-0, 1920x1080 at 0,0      -> the 24" wall
~/.nora/start-kiosk.sh    # HDMI-1, 1024x600 at 1920,0    -> the 10.1" touchscreen
```

To pick up a change that alters the *launch* (a URL change, a new flag), the running
Chromium must be killed and relaunched — a page reload is not enough:

```bash
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 \
  "pgrep -af 'chromium.*chromium-wall'"          # find the exact PID first
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 \
  "kill <pid>; DISPLAY=:0 nohup ~/.nora/start-wall.sh >/dev/null 2>&1 &"
```

Simulated touch, for confirming the kiosk actually drives the wall:

```bash
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 \
  "DISPLAY=:0 xdotool mousemove 2200 300 click 1"
```

> The Pi runs the **X11** session, not Wayland (`install-pi.sh` §6 switches it).
> That is what makes `xdotool`, `scrot` and per-output window placement work at
> all. Side effect: Raspberry Pi Connect's screen sharing is Wayland-only and stays
> broken; Remote Shell and plain SSH are unaffected.

---

## Checking from the inside

```bash
S="ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253"

$S "cd ~/Nora_Home && docker compose ps"                    # all services
$S "cd ~/Nora_Home && docker compose logs web --tail 60"
$S "cd ~/Nora_Home && docker compose exec -T web python manage.py check"

# What the app itself believes right now — better than guessing from a screenshot.
$S "cd ~/Nora_Home && docker compose exec -T web python manage.py shell -c \"
from nora_home.ui.scene import current_scene; print(current_scene())\""

$S "cd ~/Nora_Home && docker compose exec -T web python manage.py shell -c \"
from nora_home.core.registry import registered_apps
[print(a.title, a.nav, a.has_page, a.url) for a in registered_apps()]\""

curl -sk https://192.168.1.253/home/health/ | python3 -m json.tool
```

---

## What this cannot catch

Be honest about the boundary — it is why eight stories sat at *built, unproven*.

| Reachable this way | Not reachable this way |
|---|---|
| Routes, templates, 500s | Whether text is *legible* to a person at 3 metres |
| Computed CSS, real pixel geometry | Whether a design reads as charming or generic |
| Websocket connect / heartbeat | Physical touch calibration on the panel |
| What the app believes (shell) | Whether animation holds up over hours, not minutes |
| Both screens' rendered output | Slack / AI / MCP against live third-party services |

When a check is not possible, say so plainly and mark the story *built, unproven*
rather than *Complete*.

---

## Before calling something done

1. `manage.py check` clean, locally **and** on the Pi.
2. Deployed — actually rebuilt, not hot-copied.
3. Seen working: a screenshot, a measured value, or a shell query. Not a diff.
4. The *reported symptom* re-tested, not just the code path you believed was wrong.
5. `docs/progress.md` updated in the same commit ([`../CLAUDE.md`](../../CLAUDE.md) § 0).
