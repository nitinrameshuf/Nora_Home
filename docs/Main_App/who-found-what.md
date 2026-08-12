# Who found what

Every mistake, bug, invented rule and piece of drift in this project, sorted by
**which mechanism caught it**: the user, an agent, or the automated QA layer.

Kept separately from `progress.md` because the pattern only shows when the three
are read side by side. Each catches a different class of defect, and none of them
catches the others' — which is the argument for keeping all three.

---

## Summary

| Found by | Items | Catches | Blind to |
|---|---|---|---|
| **The user** (§1) | 25 | Invented rules, over-claims, anything that looks wrong on a real screen | Nothing structural — but only sees what it renders |
| **An agent** (§2) | 18 | Wiring, crashes, migration graphs, anything reachable by running the thing | Its own assumptions; taste; whether a rule was ever agreed |
| **QA / the suite** (§3) | 6 | Accessibility, contrast measured from pixels, regressions | Anything nobody wrote a check for; and it lies when the tool is wrong for the medium |

**The one-line version:** the agent finds what breaks, QA finds what regresses,
and the user finds what was never right in the first place.

---
---

# §1 — Found by the user

The most expensive class, because these survived agent review, shipped, and
needed a person to look at a screen and say so.

---

## A. Constraints invented by an agent, then quoted back as settled

The most expensive class, because each one shaped months of downstream work
before anyone checked whether it had been agreed.

**A1. "The 24" is read from ~3 metres."** *(2026-08-08 — "i want that 24inch
display to be used like a 24inch monitor, i did not ask for it to be read form 3
meter away, regular monitor level is ok")*

Sat in `CLAUDE.md` §1 under **Hardware**, formatted as a measured fact about the
room. It was the sole justification for a fifth surface, a hard-coded wall type
scale, CSS `zoom` stored in `HouseSetting`, a Settings → Screens panel, and
`nora_home/ui/zoom.py`. Removing the sentence removed the need for all of it.

**A2. "There is deliberately no npm, no bundler, and no framework."**
*(2026-08-08 — "i didnt make that rule")*

Both stated premises were false. The Pi **already** built Docker images on every
`./nora up` and `./nora upgrade`. And a house app is not hot-inserted into a
running Django process — `INSTALLED_APPS` cannot change without a restart, which
is exactly why `install_app` shells out to fresh subprocesses. "The Pi should
never run a build" described something that had never been true.

**A3. The five-surface model itself.** Followed from A1. Device class was decided
**server-side from a User-Agent regex**, and each of five surfaces got its own
hard-coded type scale — so a 13" laptop and a 32" 4K monitor rendered
byte-identical type.

**A4. The zoom setting.** Built in response to the user asking for a way to fix
the wall's size. It is a *symptom*: it exists because the layout could not
respond on its own. *(2026-08-08 — "even screen zooming is not magically
happening, like facebook or netflix or other professional apps just snap to
size")*

**A5. The 10.1" as "a small touch screen."** Characterised in the docs as a
breakpoint of the same app. *(2026-08-08 — "10.1 inch touch screen was meant to
be a futuristic control device for the page displayed in the 24inch monitor…
when no one is around, use 10inch display to display fun animation etc.")* It is
a separate product with its own job, not a responsive variant.

**Audit result.** Asked which *other* rules were invented: across all of
`CLAUDE.md`, exactly **three** decisions recorded having been put to the user —
HTTPS/self-signed/nginx-only, passwordless including `/admin/`, and DPMS blanking
both screens. Everything else in §4 and §6 was asserted by an agent in a voice
indistinguishable from settled law. On review the user *kept* Mongo, RabbitMQ and
Levels — so they were not wrong, they were simply never distinguishable from
preference.

---

## B. Work reported complete that was not

**B1. Story 41 claimed Complete without the observe pass.** *(2026-08-07 — "did
you add example tasks on the board and see it to completion to know it is all
working well?")* The honest answer was no. The database held **0 live tasks and
0 sound deliveries ever**. The project's own status vocabulary says Complete
means *observed working*.

**B2. Docs claimed updated when they were not.** *(2026-08-07 — "docs updated?
both for current app and for any future apps that may need to use the Todo
functionality?")*

**B3. Ten commits shipped with no doc change at all.** *(2026-08-08 — "your
context seems to have degraded, we need to review context and md files to ensure
its updated before moving on")* `CLAUDE.md` §0 requires docs in the *same
commit*. Four separate claims in the docs were false by then, including
architecture.md asserting the queue design prevents an outage it does not
prevent.

**B4. `./nora screens` reported success while doing nothing.** It sent
`ctrl+shift+R` via `xdotool`, which Chromium ignores in `--kiosk`. Confirmed by
the nginx access log showing zero requests across several "successful" runs.

---

## C. Defects that shipped to real screens

**C1. The 24" rendered enormous and overflowing.** *(2026-08-07 — "the laptop
and 10 inch display ui is fine, but 24inch window is all zoomed in and text looks
huge and overflowing")* Root cause was two-part: the invented 3-metre premise,
and `--nav-width: 244px` / `--tap: 44px` being **pixels** while type grew 1.6×,
so the sidebar held laptop width while its labels clipped.

**C2. "Wall" appeared as a fourth family member.** *(2026-08-07 — "there is
nitin, priya, everybody, whats that other user named wall?")* "Everyone" and
"Wall" change *what you are looking at*, not *who you are*, but sat in the same
flat list as three people.

**C3. The whole UI read as unprofessional.** *(2026-08-08 — "I dont like the UI,
base or todo, it looks too hackey and not professional")* Then, precisely: *"the
widgets are oddly sized, the lighting is bad, the spacing is abnormal… the text
sizes are not organized in parts of the app."* Each had a mechanical cause —
cards sizing to content with no row unit; translucent panes over a moving
gradient so a card's colour depended on what was behind it; eleven unrelated gap
values; and Todo setting its own type sizes independently of the base app.

**C4. Elements did not scale across devices.** *(2026-08-08)* Measured: `clamp()`
used **once** in 2,615 lines, `@container` **never**, `dvh` **never** (five uses
of `100vh`, which hides a row under the iOS URL bar), 128 hard-coded pixel
values, three hard-coded type scales.

**C5. Tofu boxes on every task card.** `&#128101;` and `&#128451;` are emoji, and
the Pi has no emoji font. Visible on the wall and kiosk on every card.

**C6. Text illegible across most of the app, in both themes.** *(2026-08-03 —
"text is not legible in many cases, in either theme")* Took **five attempts**,
four of them wrong, and the user rejected the mechanism twice before the right
one was found — including *"opacity is the wrong lever regardless of how it's
tuned."*

**C7. The living background stopped living.** *(2026-08-03 — "thematic elements
are barely visible now, know? day, night, seasons?")* A legibility fix had
flattened every pane to one alpha, undoing the design's entire premise.

**C8. "Add a widget" silently broken** by the bot's own script. *(2026-08-03 —
"Add a widget functionality is not working.")*

**C9. Stale buttons on the 10.1" display**, which turned out to hide three dead
features behind them. *(2026-08-04 — "Remove the stale buttons from the 10.1
display")*

---

## D. Lessons recorded, then not applied

The sharpest category: the project *wrote down* the answer and then did not
generalise it.

**D1. Ragged card grids — reported twice, weeks apart.**
- *2026-08-04*: "What's this boxes of varying sizes, it just looks bad." About
  **Settings**. Fixed, and the lesson written into `progress.md`: *"Cards of
  unequal height in an auto-fill grid always look ragged; no amount of padding
  tuning fixes the arrangement."*
- *2026-08-08*: "the widgets are oddly sized." About the **home dashboard** —
  the identical defect, on the more-viewed page, never touched.

**D2. Pixel values in a scaling layout.** Story 39 found and fixed Gridstack's
`cellHeight: 80` for exactly this reason. `--nav-width` and `--tap` were left as
pixels and caused C1.

**D3. Clock-dependent tests.** Two were found on 2026-08-06 and the rule written
into `testing.md`. `test_speech.py`, written *after* that, reintroduced it — and
two tests in that same file did it correctly while three did not. Passed by day,
failed at 00:05.

---

## E. Process failures

**E1. `.env` tracked in git for two days.** Every `git pull` on the Pi silently
replaced the house's real configuration with laptop defaults — settings module,
database, timezone, ports, and the real Slack and MCP tokens. It happened twice
in one session before anyone understood why.

**E2. A billable API call inside the unit suite.** `./nora test` on the Pi
inherited the live `NORA_HOME_TTS_PROVIDER=groq` from Compose and called Groq for
real. It surfaced *only* because two tests asserting the degraded path failed
with genuine WAV bytes; written any looser it would have been silent.

**E3. Deleting the tracker silently stripped every dashboard.** Stored layouts
still referenced its widgets, so 3–4 tiles vanished from every home screen
including the wall — and this was **documented approvingly** in the commit as
graceful degradation.

**E4. Excessive self-criticism as its own defect.** *(2026-08-08 — "what
stupidity, if you are working on it, you are expected to do what is needed to get
the job done. not worry about always on at that point")* Blanking a screen
mid-work is the job, not an incident to apologise for.

---

## What §1 says about agent review

1. **Nothing here was found by reading code.** Every item came from looking at a
   real screen, running the thing, or asking who agreed to a rule.
2. **Invented constraints are the most expensive category** and the hardest to
   see, because they get quoted forward as fact. A rule with no name attached
   should be treated as a proposal.
3. **A recorded lesson is not an applied lesson.** D1–D3 were all written down
   before they recurred somewhere else.
4. **"Done" claimed from a passing test is not done.** B1 and B4 both reported
   success while the observable world disagreed.

---
---

# §2 — Found by an agent

Almost all of these came from **running the thing**, not reading it. That is the
distinction worth preserving: agent review of agent code is weak, but agent
*execution* of agent code is strong.

## F. Found only by actually running it

**F1. The app registry was silently empty.** Django picks an app's config by
inspecting `AppConfig` subclasses in `apps.py`. Because that file also imports
`NoraAppConfig`, there were always two candidates, and with no tie-breaker Django
quietly fell back to a plain `AppConfig` — so nav and the app directory were
blank with no error anywhere. Fixed with `default = False` plus `__init_subclass__`.

**F2. Multi-line `{# #}` template comments render as visible text.** Django's
`{# #}` is single-line only. Visible on the page; invisible in review.

**F3. `install_app` could not migrate the first app added in a session.** It
called `makemigrations` in-process, but the process's app registry was already
populated from `.env` *as it stood before* `_register()` rewrote it. Django never
hot-reloads `INSTALLED_APPS`, so the new app was invisible and it failed with
`No installed app with label 'workout'` — one step into the documented flow.
Fixed by shelling out to fresh subprocesses.

**F4. The reference app referred to itself in seven files.** Following the
documented four-step copy recipe produced `AlreadyRegistered` on first run.

**F5. `UnicodeEncodeError` on every management command** under a non-UTF-8
console. Found one (a checkmark), fixed only that, then hit a second (an arrow) —
which is why all `stdout.write()` calls were then grepped and fixed together.

**F6. The git-clone install path had never been executed**, only its local-path
sibling. Running it end to end confirmed the clone mechanics and the
`nora-<name>` → `<name>` prefix convention.

**F7. Celery looked broken for days and never was.** `worker` and `beat`
inherited the Dockerfile's `HEALTHCHECK`, which curls the *web* role's port — a
check that can never pass for a process running no HTTP server. It sat
`unhealthy` with a 473-long failing streak while the worker pinged instantly.

**F8. `bootstrap_home`'s `_storage()` caught only `StorageUnavailable`**, not the
Pi's actual MinIO signature-mismatch error — so it was silently killing
everything after it, including the integration-seeding step.

**F9. A billable Groq call inside the unit suite.** See §1 E2 — found by an agent,
but only because two tests asserting the degraded path failed with real WAV bytes.

**F10. Verification code as the bug.** Chased "leftover test litter" for over an
hour. `Task.objects.filter()` without `.alive()` counts soft-deleted rows;
`.alive()` had been 0 the whole time. Nothing was wrong except the check.

## G. Found by reasoning about the system

**G1. A migration naming a node no installed app can supply does not degrade.**
Deleting the tracker would have left two Todo migrations depending on
`('tracker', '0001_initial')`; Django refuses to build the graph at all and every
management command dies with `NodeNotFoundError`.

**G2. `RENAME TABLE` carries rows, primary keys, indexes *and* rewrites foreign
keys in referencing tables** on both MySQL and SQLite — which is what let an
irreversible migration converge in one statement instead of
create-copy-repoint-drop. Rehearsed on a throwaway `nora_rehearsal` database
before touching production.

**G3. Unlayered CSS beats layered CSS whatever the specificity.** The cascade
compares layers before it looks at selectors.

**G4. `{% block head %}` comes after the base `<link>`s**, so per-page sheets
override anything linked above them.

**G5. `collectstatic` walks everything under `static/`** and
`ManifestStaticFilesStorage` rewrites `@import` targets in every `.css` — which
turned a Tailwind source file into `MissingFileError` and took the web container
down on boot, with three other services refusing to start behind it.

## H. Agent-caused regressions, caught by an agent

**H1. Deleting the tracker stripped every dashboard.** See §1 E3. Worth listing
twice: it was *found* by an agent and also **documented approvingly** as graceful
degradation in the same commit — the review and the defect were the same act.

**H2. `dev.py` is not hermetic.** It layers on `base.py`, which reads the
database from `.env`, so the suite tried to create `test_nora_home` on the Pi's
MySQL and errored — while passing on a laptop.

**H3. `run-tests.sh` must pass `--ds`.** pytest-django's precedence is `--ds`,
then the environment variable, then the ini file — so `pyproject.toml` loses
inside a container that exports `config.settings.pi`.

---
---

# §3 — Found by QA and the test suite

Six items, and the third one is the most important thing in this file.

**Q1. A checkbox with no accessible name.** The overnight schedule's toggle used
a `<div>`, not `<label for>`, so it had no accessible name and tapping its text
did nothing — on a touchscreen, that is the entire interaction. *(First run of
`./nora qa`, 2026-08-04.)*

**Q2. The light theme unreadable at dusk** — near-black text on the evening sky,
**2.06:1** against a floor of 3.0. Not a stray colour: `nh-scene.css` drove the
sky from `data-daypart` with no `data-theme` branch, so three of four dayparts
were dark whatever the theme said. Anyone tapping "Theme" got it.

**Q3. axe's own contrast rule is unusable in this app — and believing it would
have made things worse.** axe composites translucent panes onto the nearest
opaque ancestor. This app paints a living gradient behind everything with
`backdrop-filter` over it. So axe reported kiosk tiles at **1.95:1** against
`#b4b5b6` — a grey that appears nowhere on screen. Measured from actual rendered
pixels: **18:1**. Acting on the tool would have meant "fixing" perfectly readable
text. Contrast has been measured from pixels ever since.

**Q4. `.todo-card` had no glass pane at all**, unlike every other surface in the
house, measuring as low as **2.04:1** in dark theme. Found by Story 41's 87 new
Todo browser tests — after a whole session of unit tests that could never have
seen it.

**Q5. Three clock-dependent tests in `test_speech.py`.** Caught by the suite
itself, but only because it happened to run at 00:05. Passed all day.

**Q6. Regression cover that has since paid off** — `test_displays.py` asserts
every kiosk action has a wall handler; `test_house_apps.py` walks every registered
app's source with `ast`. Both exist because of earlier defects in this file.

## What §3 says about tooling

- **A green tool is not a correct tool.** Q3 is the case: an industry-standard
  accessibility engine confidently reported a number derived from a colour that
  does not exist on screen. The medium (translucency over a moving gradient) was
  outside its model.
- **Browser tests see a class of bug unit tests structurally cannot.** Q1, Q2 and
  Q4 are all invisible to 900+ passing unit tests.
- **QA only finds what someone wrote a check for.** Every item in §1 got past a
  green suite.

---
---

# What the three columns say together

1. **They do not overlap.** The agent finds what breaks, QA finds what regresses,
   and the user finds what was never right. No column would have caught the
   others' items.
2. **The user's column is the one that should shrink**, and the way to shrink it
   is not more review — §1 shows review does not catch these. It is deploying and
   looking, asking who agreed to a rule, and refusing to call something done from
   a passing test.
3. **Running beats reading, in every column.** §2 is almost entirely execution;
   §3 is entirely execution; §1 is a person looking at a real screen.
