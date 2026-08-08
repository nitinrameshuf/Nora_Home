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
| Sudo | passwordless (`scripts/lib/pre-provision-pi.sh` installed a validated NOPASSWD entry) |
| App login | none — passwordless by design; tap a name at `/accounts/switch/` |

**On these being written down.** There is no secret here: a private RFC1918 address,
a username, and the *path* to a key that lives on the dev machine. The key itself is
not in this repo and must never be. This is recorded deliberately so an agent can
verify its own work without asking, and **it does not need flagging every time it is
used** — using it as documented is the expected workflow, not something to check in
about.

---

## The test suite

`pytest`, at `tests/`, one file per subsystem. ~500 tests, ~2 seconds. It needs no
containers, no network, and no credentials: SQLite, the in-memory channel layer,
eager Celery. That is deliberate — it must give the same answer on a laptop and on
the Pi, rather than depending on which services happen to be up.

```bash
./scripts/run-tests.sh              # everything
./scripts/run-tests.sh houselog     # one subsystem (tests/test_houselog.py)
./scripts/run-tests.sh -k escalate  # anything else pytest understands
make test                           # same thing
```

On the Pi, run it inside the container so it uses the same Python and settings the
house actually runs on:

```bash
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 "cd ~/Nora_Home && ./nora test"
```

`pytest` and `pytest-django` are installed in the production image on purpose
(`requirements/test.txt`) so this works on the machine the house actually runs on.

The suite runs under **`config.settings.test`**, which is pinned rather than
derived — SQLite, locmem cache, in-memory channel layer, eager Celery, object
storage and Mongo off, and the reference house app always installed. Nothing in
it reads the environment. The report header names the module (`test · sqlite3`)
because getting this wrong is the failure this suite has actually hit, twice:

- **`dev.py` is not hermetic.** It layers on `base.py`, which reads the database
  engine, cache, and house apps from `.env`. On the Pi that says MySQL, so the
  suite tried to create `test_nora_home` and every database test errored on a
  missing grant — while the identical command passed on a laptop. That is what
  `config.settings.test` exists to stop.
- **`run-tests.sh` has to pass `--ds`.** pytest-django's precedence is `--ds`,
  then the `DJANGO_SETTINGS_MODULE` *environment variable*, then the ini file —
  so `pyproject.toml` loses inside the container, where the image exports
  `config.settings.pi`. `--ds` is the only level that beats the environment.

Both were found by running the suite where it is meant to run rather than
trusting the configuration, 2026-08-04.

To run against different settings deliberately:

```bash
NORA_HOME_TEST_SETTINGS=config.settings.pi ./scripts/run-tests.sh
```

### The report is the point

Raw pytest output is hundreds of lines, and an agent reading it back over SSH pays
for every one. So `conftest.py` at the repo root replaces the summary with a
fixed-size report: one line per subsystem, one line per failure carrying only its
assertion. A green run is ~20 lines however many tests there are.

```
──────────────────────────────────────────────────────────────
 NORA HOME — test report
 2026-08-04 07:58:02 · dev · sqlite3 · python 3.13.7
──────────────────────────────────────────────────────────────
  accounts                26 ok
  core                    31 ok
  todo_escalation         32 ok   1 FAIL
  ...
──────────────────────────────────────────────────────────────
 FAILURES
  test_todo_escalation.py::test_the_chain_rung_notifies_the_first_contact
    AssertionError: assert [<HouseMember: Nitin>] == [<HouseMember: Partner>]
──────────────────────────────────────────────────────────────
 1 FAILED · 495 passed · 1 failed · 0 skipped · 1.9s
──────────────────────────────────────────────────────────────
```

Full tracebacks still exist — they go to `logs/test-full.txt`. Read that file only
when the one-line assertion is not enough, which is most of the time it is not
needed. **Do not re-run with `--tb=long` reflexively**; that is the expensive path.

The report is built to never lie about a green run: a collection error (a bad
import, a missing dependency) reports `BROKEN`, and any other non-zero exit
reports `NOT OK` rather than `ALL PASSED`. If it says `ALL PASSED`, it ran.

### The suite must give the same answer at any hour

Two clock dependencies were found on 2026-08-06 by running the suite at 00:07
and getting 11 failures that had passed at 19:35. Both were the *tests* being
vague, not the code being wrong:

- A task with a due date and no due time falls due at the **09:00 default
  hour**, so nothing due "today" has come due yet before breakfast.
- Sound follows the house-wide **quiet-hours window, 22:00–07:00**, so
  `queue_alarm()` correctly refuses to make a noise at midnight.

Both fixtures now state their assumption rather than inheriting the default.
**If you write a test that depends on what time it is, pin the time.** The
cheapest way to prove a failure is clock-shaped is to re-run with the timezone
moved — `DJANGO_TIME_ZONE=Asia/Dhaka ./nora test <file>` — which is how these
were diagnosed before anything was changed.

**It happened again on 2026-08-08**, in `test_speech.py`, written *after* the
above was already documented: three tests called `speak()` and then asserted on
the Notification it creates, without pinning quiet hours — so they passed by day
and failed at 00:05. The file already contained two tests that got it right,
setting the window to `{"start": 0, "end": 24}` with a comment naming this exact
trap; the three new ones simply did not copy it.

So the rule needs to be structural, not remembered. **Prefer an autouse fixture
that pins the clock-sensitive setting for the whole module**, and let the few
tests that are genuinely *about* that setting override it — fixtures run first,
so a test setting its own window still wins. `test_speech.py::never_quiet` is the
pattern. Note the inverse of the window above: `start == end` evaluates as
`start <= hour < start`, which is never true, so `{"start": 0, "end": 0}` reads
as "never quiet" without being a magic pair of numbers.

Verify across timezones, not just one — `America/New_York`, `Asia/Dhaka`, `UTC`
and `Pacific/Auckland` between them cover a wide enough spread of local hours
that a surviving dependency shows up.

### What is covered

| File | Covers |
|---|---|
| `test_registry.py` | App discovery, nav grouping, role filtering, URL mounting, reserved slugs |
| `test_core.py` | Settings store + cache, soft delete, audit, device tokens, health probes |
| `test_accounts.py` | Roles → admin flags, quiet hours across midnight, escalation chains |
| `test_todo_escalation.py` | The ladder: climbing, stopping, audiences, resilience — and, since Story 40, that `EscalationPolicy` belongs to Todo |
| `test_ui.py` | Surface detection, the home bot, and — read as *text*, since no unit test can see a browser layout — that the wall's scale factor lives in the launch script and has not crept back into CSS, and that the layout tokens are `rem` |
| `test_houselog.py` | The House log's editorial rule — that a run of healthy snapshots and a stream of successful integration runs produce **no** entries — plus merging, filtering and the charts |
| `test_notifications.py` | Routing, dedupe, quiet hours, delivery receipts, retries |
| `test_telemetry.py` | Series, thresholds, alert suppression, history windows |
| `test_displays.py` | The bus, heartbeats, and **every kiosk action having a wall handler** |
| `test_integrations.py` | Scheduling, exponential backoff, failure alerting, the weather provider |
| `test_scene.py` | Season, real sunrise/sunset dayparts, weather bucketing |
| `test_dashboard.py` | Widget contract, layout persistence, the save endpoint's validation |
| `test_ui.py` | Surface detection for all five screens, the home bot |
| `test_pages.py` | Every page requested for real; the passwordless switcher |
| `test_house_apps.py` | The contract *every* house app must satisfy — see below |

### Conventions

- **One file per subsystem**, named `test_<subsystem>.py`. The report groups by it.
- **A test name is a sentence.** `test_a_miss_breaks_the_streak`, not `test_streak_2`.
- **Say why in the docstring when the why is not obvious** — particularly when the
  test exists because something already broke once. Several here are regression
  guards for bugs in `progress.md`, and the docstring is where that link lives.
- **Never depend on the wall clock.** Fixed dates, and `make_member` disables quiet
  hours by default. A routing test written without that passed all day and failed
  at 22:00 — it was caught while writing this suite, not in production.
- **Nothing reaches the network.** Integrations are driven with recorded payloads.

---

## The QA suite — a real browser

`./nora qa`. 226 checks (139 platform, 87 Todo's own — Story 41), ~8 minutes,
run **from a laptop against a running house** (not inside the Pi's container —
no browser there, and testing the house from outside is how anyone actually
uses it).

```bash
./nora qa                        # the Pi
./nora qa https://localhost      # a house running here
./nora qa -k kiosk               # one area
```

This is the layer `./nora test` cannot reach. The fast suite never renders a
page, never runs a line of the 1,381 lines of JavaScript that ship to browsers,
and never looks at a pixel — which is where every user-visible bug in this
project has lived while the unit tests stayed green.

| File | Checks |
|---|---|
| `test_smoke.py` | Every page opened for real: console errors, failed requests, blank renders, sideways scroll, unrendered template syntax, `window.NoraHome` intact |
| `test_journeys.py` | Add a widget **and reload**, save Settings, the profile menu, every nav link resolving, the five surface sizes |
| `test_screens.py` | The wall and kiosk open **at once** — a kiosk tap moving the wall's iframe, the kiosk staying on its own buttons, no dead controls, no error toast |
| `test_accessibility.py` | axe-core on every page, plus contrast measured from pixels across themes, dayparts, seasons and both screen sizes |
| `test_todo_qa.py` | Todo's own pages (not in `PLATFORM_PAGES` — Level 2, mounted at its own top-level slug): board, calendar, reporting, search, labels, settings, create, system. Creating, completing and archiving a task **through the browser and reloaded**; the calendar renders a real grid; Reporting never says "could not load" and every card is a chart, a table, or an explicit empty sentence; no sideways scroll at the five real sizes; card-title contrast across every theme × daypart |

### Contrast is measured from pixels, not from the DOM

axe's own `color-contrast` rule is **switched off deliberately**. It composites
translucent panes onto the nearest opaque ancestor, and this app paints a living
gradient behind everything with `backdrop-filter` over it — so axe reported the
kiosk tiles at 1.95:1 against `#b4b5b6`, a grey that appears nowhere on screen.
Measured from the actual rendering, the same text is 18:1.

**Taking axe at its word would have meant "fixing" readable text and making it
worse.** `measure_text_contrast()` in `tests/qa/conftest.py` screenshots the
element and compares the glyphs to their background. It was validated by
deliberately breaking a colour and confirming it caught it: 18.25 as shipped,
2.81 when broken. Every other axe rule stays on — they read the DOM, which axe
is good at, and one of them found a checkbox with no label.

### Tuning a colour: measure, do not eyeball

The light theme was fixed this way and the method is worth copying. The veil over
the scene started at 0.86 — it passed contrast comfortably and washed the whole
living background away, which defeats the point of having one. Sweeping the value
against real rendered contrast found a sharp cliff between 0.38 and 0.46 (night
collapses to 1.92:1) and a wide safe shelf above it, so 0.54 buys most of the
scene back at 8.19:1.

Neither the cliff nor the headroom was visible by eye. Drive the page with
`page.add_style_tag()`, sweep the value, and print the measurements — a dozen
lines, and it turns a taste argument into a table.

### Writing QA tests

Fixtures in `tests/qa/conftest.py`: `signed_in`, `console_errors`,
`visit(page, path)`, `open_actions_menu(page)`, `measure_text_contrast(...)`,
`house_url`.

**Never wait on `networkidle`.** The wall and kiosk hold a websocket open for
their whole life and poll the weather every few minutes, so the network is never
idle and the wait times out after 30s. `visit()` exists for this; using
`networkidle` is what made the first run take five and a half minutes and report
failures that were nothing but a bad wait condition.

Page actions — "Add a widget", "Rearrange", the switcher — live inside the
profile dropdown, so they are in the DOM but not visible until it is opened.
`open_actions_menu()` does that. Worth knowing before concluding a button is
broken.

### Known QA gaps

- **Chromium only.** WebKit cannot reach this Pi (see above).
- **Nothing here judges how it looks.** Contrast is not legibility at three
  metres, and no tool has an opinion on whether a design is any good.
- **This Mac has neither Python nor a browser toolchain.** `test_todo_qa.py`
  (Story 41) was written and debugged by copying files to the Pi over `scp`
  and running Playwright from a one-time venv there (`~/.nora-qa-venv`), not
  from a laptop. It is the same "real browser against a running house" pattern
  the rest of this section describes, on the one machine that had a viable
  Chromium build (arm64) already reachable.
- **If a test writes data, `Task.objects.filter(...)` is not "does it still
  exist".** `SoftDeleteModel.delete()` sets `deleted_at`; it does not remove
  the row. A cleanup-verification chase that cost over an hour during Story 41
  turned out to be checking litter with a query that never called `.alive()`
  — the rows it kept "finding" were successfully deleted history, not survivors.
  When a test's own cleanup and a manual check of "did it work" disagree for
  longer than it takes to re-read the check, suspect the check first.

### Known gaps

Be honest about these rather than implying the suite proves more than it does.

- **No Celery beat / worker test.** Tasks are called directly, and
  `test_scheduled_work.py` checks that every scheduled entry imports, is
  registered, and is routed to a queue the worker consumes — but nothing here
  drives a real broker. Beat firing on the Pi is confirmed separately (279 health
  snapshots), not by this suite.
- **No Slack, AI, or MCP round-trip.** No credentials exist. The Slack channel is
  tested through its `is_configured()` gate only.
- **No Mongo or MinIO.** `nora_home.datastores` is untested; both are optional
  dependencies the house degrades without.
- **No websocket consumer tests.** The bus is tested, and the message-type contract
  between kiosk and wall is tested, but the consumers themselves are not driven.
- ~~**`example_habit` imports `nora_home.tracker.models` directly**~~ — **fixed
  2026-08-04**, and both apps have since been deleted (Story 28, Story 40). The
  helpers it needed were added to that app's own API
  (`streak_for`, `is_done_today`, `history_for`, `completion_stats`,
  `trackable_for`), all five files use them, and `KNOWN_MODEL_IMPORT_DEBT` is
  empty. Confirmed by copying the reference app into a scratch app and running the
  contract tests against it — clean.
- **None of it says anything about how the house looks.** See "What this cannot
  catch" below. A green suite is not a deployed, seen-working feature.

---

## The deploy loop

Docs-only changes need no rebuild — `git pull` on the Pi is enough. Anything under
`nora_home/`, `templates/`, `static/`, or `config/` needs the rebuild, because
static files are collected into the image.

```bash
# on the dev machine
git add -A && git commit -m "..." && git push origin main

# on the Pi — everything operational goes through ./nora
ssh -i ~/.ssh/nora_pi ckstation@192.168.1.253 "cd ~/Nora_Home && ./nora upgrade"
```

`./nora upgrade` backs up, pulls, rebuilds, migrates, restarts, and waits for the
health endpoint before returning — so a failure stops there rather than leaving a
half-started house. `./nora help` lists the rest.

> ### `docker compose up -d web` is not a deploy
>
> Recreating `web` alone leaves `worker`, `beat` and `slack` on the previous
> image, and **they fail silently rather than loudly** — a container keeps the
> code it started with, and old code simply does not know about the new field.
>
> This cost a debugging detour during Story 37: a Slack reminder arrived with no
> buttons, no error anywhere. Notification *rendering* happens in the **worker**,
> which was still on the previous image and ignored the `slack_actions` it had
> never heard of. Rule of thumb for which container to recreate:
>
> | You changed | Recreate |
> |---|---|
> | A view, template, or static file | `web` |
> | A Celery task, or anything a task calls — notifications, reminders, escalation | `worker` |
> | A schedule in `beat_schedule` | `beat` |
> | A Slack command, button, or dispatch | `slack` (and `worker`, if rendering moved) |
> | Anything you are unsure about | all of them: `./nora recreate` |

> ### If the house suddenly looks empty after a deploy, it is not
>
> `.env` was tracked in git for two days (fixed 2026-08-05 — it and `.env.*` are
> ignored now), and while it was, the `git pull` inside `./nora upgrade` replaced
> the house's real configuration with `.env.example`'s laptop defaults. The
> rebuild that followed brought `web` up on a fresh, empty SQLite database in its
> own container layer, because **there is no volume for `db.sqlite3`**.
>
> The specific cause is fixed; the shape of the failure is worth remembering,
> because anything that changes `.env` produces it. **It looks exactly like the
> house losing all its data, and it is not.** MySQL still holds every row, and
> any container you did *not* recreate is still using it. Do not restore from a
> backup on this evidence alone — ask what the app is actually connected to:
>
> ```bash
> docker compose exec -T web python manage.py shell -c "
> from django.conf import settings; print(settings.DATABASES['default'])"
> ```
>
> If it says sqlite and you expected MySQL, rebuild `.env` from a container that
> has not been recreated — it kept the environment it started with, which makes
> it the best record of the correct values — then `./nora recreate`:
>
> ```bash
> docker inspect nora-home-worker-1 --format '{{range .Config.Env}}{{println .}}{{end}}'
> ```

The ones worth knowing while debugging:

| Command | For |
|---|---|
| `./nora recreate` | **After editing `.env`.** A restart will not do it — a running container keeps the environment it started with. This has cost a session |
| `./nora status` | Services and the health endpoint in one |
| `./nora logs [service]` | Follow logs |
| `./nora test` | The suite, inside the container |
| `./nora manage <cmd>` | Any management command |
| `./nora screens` | Hard-reload the wall and kiosk after a template change |

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

The two Chromium instances are launched by scripts `provision-pi.sh` generated:

```bash
~/.nora/start-wall.sh     # HDMI-0, 1920x1080 at 0,0      -> the 24" wall
~/.nora/start-kiosk.sh    # HDMI-1, 1024x600 at 1920,0    -> the 10.1" touchscreen
```

After a template or static change, the screens hold the old page until reloaded —
`./nora screens` does both. (It searches by window *title*: searching by class
matches Chromium's helper windows, not the pages, and silently reloads nothing.)

To pick up a change that alters the *launch* itself (a URL change, a new flag),
the running Chromium must be killed and relaunched — a reload is not enough:

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

> The Pi runs the **X11** session, not Wayland (`provision-pi.sh` §6 switches it).
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

1. `./scripts/run-tests.sh` green, and **a new test covering the change** — a fix
   with no test is a fix that gets re-broken.
2. `manage.py check` clean, locally **and** on the Pi.
3. Deployed with `./nora upgrade` — actually rebuilt, not hot-copied.
4. `./nora test` run again *on the Pi*, inside the container.
5. Seen working: a screenshot, a measured value, or a shell query. Not a diff.
6. The *reported symptom* re-tested, not just the code path you believed was wrong.
7. `docs/Main_App/progress.md` updated in the same commit
   ([`../../CLAUDE.md`](../../CLAUDE.md) § 0).
