# Found by the user

Every mistake, bug, invented rule and piece of drift in this project that **the
user caught, not an agent**. Kept separately from `progress.md` because the
pattern only shows up when they are read together: these are the things that
shipped, or were claimed done, or were written into the rules, and survived
until a person looked at the screen and said so.

Read it as a list of what agent self-review missed.

---

## Summary

| Class | Count |
|---|---|
| Constraints invented by an agent and stated as settled fact | 5 |
| Work reported complete that was not | 4 |
| Defects that shipped to real screens | 9 |
| Lessons recorded, then not applied elsewhere | 3 |
| Process failures | 4 |

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

## What the pattern says

1. **Nothing here was found by reading code.** Every item came from looking at a
   real screen, running the thing, or asking who agreed to a rule.
2. **Invented constraints are the most expensive category** and the hardest to
   see, because they get quoted forward as fact. A rule with no name attached
   should be treated as a proposal.
3. **A recorded lesson is not an applied lesson.** D1–D3 were all written down
   before they recurred somewhere else.
4. **"Done" claimed from a passing test is not done.** B1 and B4 both reported
   success while the observable world disagreed.
