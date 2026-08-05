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
TEXT_TARGETS = [
    ("body copy", ".card p, .setting__label, .dash-tile", WCAG_AA_NORMAL),
    ("headings", "h1, h2, .card-title", WCAG_AA_LARGE),
    ("sidebar links", ".sidebar a", WCAG_AA_NORMAL),
]


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("what,selector,threshold",
                         TEXT_TARGETS, ids=[t[0] for t in TEXT_TARGETS])
def test_text_is_readable_in_both_themes(signed_in, theme, what, selector, threshold):
    """The light theme has never been checked on real hardware (CLAUDE.md §2).
    Contrast is the part that can be checked without a person looking."""
    visit(signed_in, "/home/")
    signed_in.evaluate(f"document.documentElement.setAttribute('data-theme', '{theme}')")
    signed_in.wait_for_timeout(500)  # let the transition settle before measuring

    ratio = measure_text_contrast(signed_in, selector)
    if ratio is None:
        pytest.skip(f"no {what} on this page")

    assert ratio >= threshold, (
        f"{what} in the {theme} theme measures {ratio:.2f}:1, below {threshold}:1")


@pytest.mark.parametrize("theme", ["dark", "light"])
@pytest.mark.parametrize("daypart", ["dawn", "noon", "dusk", "night"])
def test_the_page_heading_is_readable_on_the_bare_sky(signed_in, theme, daypart):
    """The heading sits directly on the scene with no pane beneath it, which is
    what made the light theme unreadable: pane tuning could never reach it. Every
    theme x daypart combination, because the sky changes under it all day."""
    visit(signed_in, "/home/")
    signed_in.evaluate(f"""() => {{
        document.documentElement.setAttribute('data-theme', '{theme}');
        document.documentElement.setAttribute('data-daypart', '{daypart}');
    }}""")
    signed_in.wait_for_timeout(600)

    ratio = measure_text_contrast(signed_in, "h1")
    if ratio is None:
        pytest.skip("no heading on this page")

    assert ratio >= WCAG_AA_LARGE, (
        f"the heading in the {theme} theme at {daypart} measures {ratio:.2f}:1")


@pytest.mark.parametrize("daypart", ["dawn", "noon", "dusk", "night"])
def test_text_stays_readable_at_every_time_of_day(signed_in, daypart):
    """The living background changes behind the glass panes all day. Contrast
    that holds at noon and fails at night is a bug nobody sees until it is
    dark — and the wall is unattended precisely then."""
    visit(signed_in, "/home/")
    signed_in.evaluate(
        f"document.documentElement.setAttribute('data-daypart', '{daypart}')")
    signed_in.wait_for_timeout(500)

    ratio = measure_text_contrast(signed_in, ".dash-tile")
    if ratio is None:
        pytest.skip("no tiles on the home screen")

    assert ratio >= WCAG_AA_NORMAL, (
        f"home screen text at {daypart} measures {ratio:.2f}:1")


@pytest.mark.parametrize("season", ["winter", "spring", "summer", "autumn"])
def test_text_stays_readable_in_every_season(signed_in, season):
    visit(signed_in, "/home/")
    signed_in.evaluate(
        f"document.documentElement.setAttribute('data-season', '{season}')")
    signed_in.wait_for_timeout(500)

    ratio = measure_text_contrast(signed_in, ".dash-tile")
    if ratio is None:
        pytest.skip("no tiles on the home screen")

    assert ratio >= WCAG_AA_NORMAL, (
        f"home screen text in {season} measures {ratio:.2f}:1")


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


def test_the_kiosk_tiles_are_readable(signed_in):
    """1024x600 — the real panel. These are touch targets read at arm's length
    in a hallway, so they get the large-text threshold."""
    signed_in.set_viewport_size({"width": 1024, "height": 600})
    visit(signed_in, "/home/displays/kiosk/")

    ratio = measure_text_contrast(signed_in, ".kiosk-tile__title")
    if ratio is None:
        pytest.skip("no kiosk tiles")

    assert ratio >= WCAG_AA_NORMAL, f"kiosk tiles measure {ratio:.2f}:1"


def test_the_kiosk_hint_text_is_readable(signed_in):
    """The smaller second line under each tile — the first thing to fail when a
    palette is nudged."""
    signed_in.set_viewport_size({"width": 1024, "height": 600})
    visit(signed_in, "/home/displays/kiosk/")

    ratio = measure_text_contrast(signed_in, ".kiosk-tile__hint")
    if ratio is None:
        pytest.skip("no kiosk hint text")

    assert ratio >= WCAG_AA_NORMAL, f"kiosk hint text measures {ratio:.2f}:1"


def test_the_settings_labels_are_readable(signed_in):
    """axe flagged these at 3.25:1; measured from pixels they are fine. Kept as
    a real check so a future palette change is caught honestly."""
    visit(signed_in, "/home/settings/")

    ratio = measure_text_contrast(signed_in, ".setting__label")
    if ratio is None:
        pytest.skip("no settings rows")

    assert ratio >= WCAG_AA_NORMAL, f"settings labels measure {ratio:.2f}:1"
