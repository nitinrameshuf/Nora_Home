# testing.md — Habits (`houseapps.example_habit`)

**This file is also the template.** Every house app needs one, at
`docs/House_Apps/<app>/testing.md` — `install_app` warns when it is missing and
`tests/test_house_apps.py` fails without it. Copy this file, delete what does not
apply, and keep the four headings.

The platform's own suite is documented in
[`../../Main_App/testing.md`](../../Main_App/testing.md). Read that first: it covers
how to run tests, how the compact report works, and how to verify on the Pi. This
file is only about *this app*.

---

## What the platform already tests for you

Do not re-test these. `tests/test_house_apps.py` walks every installed app and
checks them automatically, so this app gets them for free — and so will yours:

- The app is discovered, has a slug, title, and description, and its category and
  minimum role are real ones.
- It does not claim a URL prefix the platform reserves.
- Its page loads (200, signed in) if it declares one.
- Every widget, dashboard card, and wall panel it declares actually loads, and
  wall panels are `wall_safe`.
- Its kiosk controls are well-formed and their paths resolve.
- Every model inherits `TimeStampedModel`.
- It has an initial migration.
- It does not read `os.environ` directly, and does not import another app's models.
- It has this file, and a `README.md` beside it.

The scheduling, escalation, notification, and telemetry the app *uses* are tested
in the platform suite too. An app should test **its own logic**, not the tracker's.

---

## What this app tests

Habits is the reference app, so its own logic is deliberately thin: a `Habit`
model whose `save()` registers a `Trackable`, two widgets, a wall panel, an MCP
tool, and a weekly Celery task that records a completion-rate series.

| Behaviour | Where |
|---|---|
| Saving a habit registers a trackable at `(habits, <pk>)` | `tests/test_house_apps.py` (contract) + platform `test_tracker.py` |
| Editing a habit updates rather than duplicating the trackable | platform `test_tracker.py::test_registering_twice_updates_rather_than_duplicating` |
| The two widgets load and render | `tests/test_house_apps.py::test_every_declared_widget_loads` |
| The wall panel is wall-safe | `tests/test_house_apps.py::test_every_declared_wall_panel_loads_and_is_wall_safe` |
| `/habits/` renders for a signed-in member | `tests/test_house_apps.py::test_the_apps_page_actually_loads` |

**Not yet covered, and worth writing if this app were real rather than a
reference**: the weekly `record_completion_rates` task's arithmetic, marking a
habit done through the view (not just through the tracker API), and the MCP tool's
output shape.

---

## Two layers: unit and browser

`./nora test` is Python only — it never renders your page or runs your
JavaScript. `./nora qa` drives a real Chromium against a running house. **Your
app needs both**, because this project's most user-visible bugs have all lived in
the second layer while the first stayed green.

| Layer | File | Catches |
|---|---|---|
| Unit | `tests/test_<app>.py` | Your logic, your models, your API calls |
| Browser | `tests/qa/test_<app>_qa.py` | Console errors, clicks that do nothing, unreadable text, broken layout on the five surfaces |

See [`../../Main_App/DEVELOPMENT.md`](../../Main_App/DEVELOPMENT.md#two-layers-and-yours-needs-both)
for the fixtures you get free — `signed_in`, `console_errors`, `visit()`,
`measure_text_contrast()`.

## How to add tests for your own app

Put them next to the platform's, as `tests/test_<yourapp>.py`, so they appear as
their own line in the report:

```python
"""Workout — sets, volume, and the weekly rollup."""

import pytest

from houseapps.workout.models import Session

pytestmark = pytest.mark.django_db


def test_logging_a_session_registers_it_with_the_tracker(member):
    """The platform owns the schedule; this app only has to hand it the record."""
    from nora_home.tracker.models import Trackable

    session = Session.objects.create(owner=member, title="Push day")

    assert Trackable.objects.filter(app_slug="workout",
                                    source_ref=str(session.pk)).exists()
```

The fixtures in `tests/conftest.py` are available to you: `member`, `adult`,
`admin_member`, `household`, `make_member`, `make_trackable`, `make_occurrence`,
`series`, `wall_display`, `kiosk_display`, `signal_recorder`. Use them rather than
building people and trackables by hand.

Then:

```bash
./scripts/run-tests.sh workout
```

---

## Verifying on the real hardware

The suite says nothing about how the app *looks* on the 24" wall or the 10.1"
kiosk. Before marking anything Complete rather than *built, unproven*, follow
[`../../Main_App/testing.md`](../../Main_App/testing.md) § Checking the real
hardware — screenshot both physical screens and confirm:

- The app's tile appears on the kiosk, and tapping it moves the wall.
- Its own kiosk control screen appears, and Back returns without disturbing the wall.
- Any wall panel is legible from about three metres.
