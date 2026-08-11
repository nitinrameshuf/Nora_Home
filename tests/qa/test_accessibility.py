"""
axe-core, run against every page.

This is the off-the-shelf half, and the best value in the suite: it is somebody
else's rule engine, maintained by people who do this full time, and it needs
almost no code here.

It exists because of a specific failure. On 2026-08-03 the dark theme shipped
with text nobody could read — "barely legible" was the report — and it took a
round of screenshots, a wrong theory about macOS transparency settings, and a
controlled WebKit-vs-Chromium comparison to sort out. axe checks contrast
automatically, on every page, in about a second.

It also catches the things a house of four will actually hit: a form field with
no label, a button that is only an icon, an image with no alt text.
"""

from __future__ import annotations

import pytest
from axe_playwright_python.sync_playwright import Axe

from tests.qa.conftest import (
    PLATFORM_PAGES,
    SCREEN_PAGES,
    WCAG_AA_LARGE,
    WCAG_AA_NORMAL,
    measure_text_contrast,
    visit,
)

pytestmark = pytest.mark.qa

ALL_PAGES = PLATFORM_PAGES + SCREEN_PAGES

# Rules worth failing a build over. axe reports far more than this; starting
# narrow and widening deliberately is what keeps the signal trusted — a suite
# that reports forty cosmetic violations gets muted, which is worse than not
# running it.
ENFORCED = {
    # NOT color-contrast. axe composites translucent panes onto the nearest
    # opaque ancestor, and this app paints a living gradient behind everything
    # with backdrop-filter over it — so axe reported the kiosk tiles at 1.95:1
    # against #b4b5b6, a grey that is nowhere on screen. Measured from real
    # pixels the same text is 18:1. Contrast is checked below instead, from
    # screenshots. Every rule kept here reads the DOM, which axe is good at.
    "label",                # a form field nobody can identify
    "button-name",          # an icon-only button, unusable by voice or screen reader
    "link-name",
    "image-alt",
    "html-has-lang",
    "aria-required-attr",
    "aria-valid-attr-value",
    "duplicate-id-active",  # two elements sharing an id breaks the JS that finds them
}


def _violations(page, only: set[str]) -> list[str]:
    results = Axe().run(page)
    found = []
    for violation in results.response.get("violations", []):
        if violation["id"] not in only:
            continue
        targets = ", ".join(
            str(node["target"]) for node in violation["nodes"][:3])
        found.append(f"{violation['id']} ({len(violation['nodes'])}x): "
                     f"{violation['help']} — e.g. {targets}")
    return found


@pytest.mark.parametrize("name,path", ALL_PAGES, ids=[n for n, _ in ALL_PAGES])
def test_page_passes_the_enforced_accessibility_rules(signed_in, name, path):
    visit(signed_in, path)

    problems = _violations(signed_in, ENFORCED)

    assert not problems, f"{name} ({path}):\n  " + "\n  ".join(problems)


# The text worth measuring: what a person actually reads on each surface.
# Class names ported to the arc-reactor component set (Story 45, Phase B) —
# `.setting__label` -> `.set-row .k`, `.dash-tile` -> `.nh-tile`, `.card-title`
# -> `.card-h h4`, `.sidebar a` -> `.rail .nav` (Story 55).
TEXT_TARGETS = [
    ("body copy", ".card p, .set-row .k, .nh-tile", WCAG_AA_NORMAL),
    ("headings", "h1, h2, .card-h h4", WCAG_AA_LARGE),
    ("nav links", ".rail .nav", WCAG_AA_NORMAL),
]


# Phase 8 (CLAUDE.md §4) deleted the light theme rather than rebuild it —
# "dark only" — and removed season from the scene entirely (Story 46: "time
# of day and real weather only"). Both used to be parametrized here; testing
# a state the house cannot enter any more was pure noise, worse than a gap,
# because a pass either way said nothing true. Dropped rather than left "for
# when it comes back" — the same rule CLAUDE.md gives the mockup itself: a
# check that looks plausible but tests nothing real is worse than no check.

@pytest.mark.parametrize("what,selector,threshold",
                         TEXT_TARGETS, ids=[t[0] for t in TEXT_TARGETS])
def test_text_is_readable(signed_in, what, selector, threshold):
    visit(signed_in, "/home/")
    signed_in.wait_for_timeout(500)  # let the scene settle before measuring

    ratio = measure_text_contrast(signed_in, selector)
    if ratio is None:
        pytest.skip(f"no {what} on this page")

    assert ratio >= threshold, f"{what} measures {ratio:.2f}:1, below {threshold}:1"


@pytest.mark.parametrize("daypart", ["dawn", "noon", "dusk", "night"])
def test_the_page_heading_is_readable_on_the_bare_sky(signed_in, daypart):
    """The heading sits directly on the scene with no pane beneath it. Every
    daypart, because the sky changes under it all day and a heading that reads
    fine at noon has failed at night before (CLAUDE.md's own 2026-08-03 story)."""
    visit(signed_in, "/home/")
    signed_in.evaluate(
        f"document.documentElement.setAttribute('data-daypart', '{daypart}')")
    signed_in.wait_for_timeout(600)

    ratio = measure_text_contrast(signed_in, "h1")
    if ratio is None:
        pytest.skip("no heading on this page")

    assert ratio >= WCAG_AA_LARGE, f"the heading at {daypart} measures {ratio:.2f}:1"


@pytest.mark.parametrize("daypart", ["dawn", "noon", "dusk", "night"])
def test_text_stays_readable_at_every_time_of_day(signed_in, daypart):
    """The living background changes behind the glass panes all day. Contrast
    that holds at noon and fails at night is a bug nobody sees until it is
    dark — and the wall is unattended precisely then."""
    visit(signed_in, "/home/")
    signed_in.evaluate(
        f"document.documentElement.setAttribute('data-daypart', '{daypart}')")
    signed_in.wait_for_timeout(500)

    ratio = measure_text_contrast(signed_in, ".nh-tile")
    if ratio is None:
        pytest.skip("no tiles on the home screen")

    assert ratio >= WCAG_AA_NORMAL, (
        f"home screen text at {daypart} measures {ratio:.2f}:1")


def test_the_wall_is_readable_at_its_own_size(signed_in):
    """The 24" is read from about three metres. Contrast is not the same thing
    as legibility at distance — no tool judges that — but it is the part that
    can be measured."""
    signed_in.set_viewport_size({"width": 1920, "height": 1080})
    visit(signed_in, "/home/displays/wall/")

    ratio = measure_text_contrast(signed_in, "body")
    if ratio is None:
        pytest.skip("the wall rendered nothing measurable")

    assert ratio >= WCAG_AA_LARGE, f"the wall measures {ratio:.2f}:1"


# The kiosk is checked at every daypart, not just whichever one is live when the
# suite runs. That is not hypothetical caution: the tile hints failed at noon
# (1.94:1) and passed at night (7.79:1), so the bug was invisible for a whole
# run and only appeared when the suite happened to be run again in daylight. A
# check on a surface whose background changes all day has to pin the background.
#
# Story 50 rebuilt the kiosk as a control desk — `.kiosk-tile__title`/
# `.kiosk-tile__hint`/`.kiosk-header strong` are the pre-Story-50 button grid.
# Every key's label is now `.hkey .lg` (the desk's illuminated square key);
# the one "header" text worth checking is the dot-matrix readout showing
# which app the wall is on, `.d-readout`. Dark is the only theme (Phase 8,
# CLAUDE.md §4), so "light" is dropped from the parametrize below too.
@pytest.mark.parametrize("daypart", ["dawn", "noon", "dusk", "night"])
@pytest.mark.parametrize("what,selector", [
    ("key labels", ".hkey .lg"),
    ("the readout", ".d-readout"),
])
def test_the_kiosk_is_readable_at_every_hour(signed_in, daypart, what, selector):
    """1024x600 — the real panel. A wall-mounted control surface read at arm's
    length in a hallway, and daylight is when someone is standing at it."""
    signed_in.set_viewport_size({"width": 1024, "height": 600})
    visit(signed_in, "/home/displays/kiosk/")
    signed_in.evaluate(
        f"document.documentElement.setAttribute('data-daypart', '{daypart}')")
    signed_in.wait_for_timeout(600)

    ratio = measure_text_contrast(signed_in, selector)
    if ratio is None:
        pytest.skip(f"no {what} on the kiosk")

    assert ratio >= WCAG_AA_NORMAL, f"{what} on the kiosk at {daypart}: {ratio:.2f}:1"


def test_the_settings_labels_are_readable(signed_in):
    """axe flagged these at 3.25:1; measured from pixels they are fine. Kept as
    a real check so a future palette change is caught honestly. `.setting__
    label` -> `.set-row .k` (Story 45, Phase B)."""
    visit(signed_in, "/home/settings/")

    ratio = measure_text_contrast(signed_in, ".set-row .k")
    if ratio is None:
        pytest.skip("no settings rows")

    assert ratio >= WCAG_AA_NORMAL, f"settings labels measure {ratio:.2f}:1"
