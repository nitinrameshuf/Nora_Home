"""
The things a person actually does, done in a browser.

Each of these is a flow the fast suite can only test in halves: it can POST the
layout endpoint and check the row, but it cannot click the button that is
supposed to send that POST. The gap between those two is where "Add a widget"
was broken for a day while every test stayed green.
"""

from __future__ import annotations

import pytest

from tests.qa.conftest import open_household_menu, set_surface, visit

pytestmark = pytest.mark.qa


def test_adding_a_widget_puts_it_on_the_screen_and_keeps_it(signed_in, console_errors):
    """The regression this suite exists for.

    It broke because `nh-bot.js` overwrote `window.NoraHome`, taking
    `csrfToken()` with it; the POST 403'd, `fetch()` did not reject, and the page
    reloaded looking like it had worked. Clicking through and *reloading* is the
    only way to tell the difference.
    """
    visit(signed_in, "/home/")

    before = signed_in.locator(".nh-tile").count()

    # No menu to open first — Story 45 Phase B moved page actions ("Add a
    # widget", "Rearrange") to render directly in the appbar. Only the
    # household switcher stays behind a click now (open_household_menu).
    trigger = signed_in.locator("[data-dash-add]:visible").first
    if trigger.count() == 0:
        pytest.skip("no widget picker on this page")
    trigger.click()
    signed_in.locator("[data-dash-picker]").wait_for(state="visible", timeout=5000)

    # Widgets already on the screen render disabled — clicking one does nothing
    # and the test would report a failure that is really its own fault.
    option = signed_in.locator(".dash-picker__item:not([disabled])").first
    if option.count() == 0:
        pytest.skip("every available widget is already on the screen")
    key = option.inner_text().split("\n")[0][:40]
    option.click()

    signed_in.wait_for_timeout(1500)
    signed_in.reload(wait_until="domcontentloaded"); signed_in.wait_for_timeout(1200)
    after = signed_in.locator(".nh-tile").count()

    assert not console_errors, "adding a widget logged: " + "; ".join(console_errors)
    assert after > before, (
        f"widget {key!r} did not survive a reload — {before} tiles before, "
        f"{after} after. The save silently failed.")


def test_the_home_screen_renders_its_tiles(signed_in):
    """A grid that renders zero tiles is what a broken widget payload looks
    like — the page still returns 200."""
    visit(signed_in, "/home/")
    signed_in.wait_for_timeout(600)

    assert signed_in.locator(".nh-tile").count() > 0, "the home screen is empty"


def test_no_widget_rendered_as_unavailable(signed_in):
    """A widget whose `payload()` raises degrades to "could not load" rather
    than 500ing — correct behaviour, and invisible to the fast suite, which
    never renders it."""
    visit(signed_in, "/home/")
    signed_in.wait_for_timeout(1200)

    body = signed_in.locator("body").inner_text()

    assert "could not load" not in body.lower(), "a widget failed to build its payload"


def test_saving_the_overnight_schedule_persists(signed_in, console_errors):
    """The Settings form, clicked rather than POSTed."""
    visit(signed_in, "/home/settings/")

    start = signed_in.locator("#wall_schedule_start")
    original = start.input_value()
    new_value = "3" if original != "3" else "4"

    # Settings has no wrapping `.settings` class any more (Story 45, Phase B) —
    # each section is its own {% nh_card %} with its own <form>, so the save
    # button has to be found relative to the field being tested.
    save = signed_in.locator("form:has(#wall_schedule_start) button[type=submit]").first
    start.fill(new_value)
    save.click()
    signed_in.wait_for_load_state("load")

    try:
        assert signed_in.locator("#wall_schedule_start").input_value() == new_value, (
            "the schedule did not save")
        assert not console_errors, "saving settings logged: " + "; ".join(console_errors)
    finally:
        # Leave the house as we found it — this runs against the real Pi.
        signed_in.locator("#wall_schedule_start").fill(original)
        signed_in.locator("form:has(#wall_schedule_start) button[type=submit]").first.click()
        signed_in.wait_for_load_state("load")


def test_the_profile_menu_closes_when_you_click_away(signed_in):
    """A native <details> now (Story 45/49's .profile-menu, member_switcher
    .html) — nh-app.js's wireProfileMenu() closes it on an outside click,
    which is the one part not already free from using <details>."""
    visit(signed_in, "/home/")

    trigger = signed_in.locator(".profile-menu summary").first
    if trigger.count() == 0:
        pytest.skip("no household switcher on this surface")
    trigger.click()
    menu = signed_in.locator(".profile-menu")
    assert menu.get_attribute("open") is not None, "the menu did not open"

    signed_in.locator("body").click(position={"x": 5, "y": 400})
    signed_in.wait_for_timeout(300)

    assert menu.get_attribute("open") is None, "the menu stayed open after clicking away"


def test_switching_to_everyone_shows_the_shared_view(signed_in):
    """"Everyone" lives in the household switcher (.profile-menu), not behind
    a separate actions menu — Story 45/49 folded who-you-are and what-you're-
    viewing into one control."""
    visit(signed_in, "/home/")

    open_household_menu(signed_in)

    everyone = signed_in.locator("form[action*='everyone'] button").first
    if everyone.count() == 0:
        pytest.skip("already in the Everyone view")
    everyone.wait_for(state="visible", timeout=5000)
    everyone.click()
    signed_in.wait_for_load_state("load")

    assert signed_in.url.rstrip("/").endswith("/home"), "Everyone did not land on the home screen"


def test_the_nav_only_links_somewhere_real(signed_in):
    """A nav entry pointing at a 404 is the failure `nora_has_page` exists to
    prevent. Worth checking against the rendered page, not just the registry."""
    visit(signed_in, "/home/")

    hrefs = signed_in.eval_on_selector_all(
        ".rail a[href]", "els => els.map(e => e.getAttribute('href'))")
    hrefs = [h for h in hrefs if h and h.startswith("/")]
    assert hrefs, "the rail has no links at all"

    broken = []
    for href in dict.fromkeys(hrefs):
        response = signed_in.request.get(href)
        if response.status >= 400:
            broken.append(f"{href} -> {response.status}")

    assert not broken, "sidebar links that do not resolve:\n  " + "\n  ".join(broken)


# label -> the surface that size actually renders as. Wall/kiosk are decided
# by URL path (SurfaceMiddleware), not viewport or UA, so they are left at
# whatever real detection gives a plain /home/ request — None, same as
# "desktop", which is honest: this suite never visits the real wall/kiosk
# URLs, so calling these two "the wall"/"the kiosk" was already aspirational.
SURFACE_FOR_LABEL = {"iPhone": "phone", "iPad": "tablet"}


@pytest.mark.parametrize("width,height,label", [
    (390, 844, "iPhone"),
    (820, 1180, "iPad"),
    (1440, 900, "laptop"),
    (1920, 1080, "the 24-inch wall"),
    (1024, 600, "the 10-inch kiosk"),
])
def test_the_home_screen_works_on_every_surface(signed_in, house_url, width, height, label):
    """Five surfaces, one codebase — the promise in CLAUDE.md §5. Checked at the
    real sizes rather than at arbitrary breakpoints.

    set_surface is required, not cosmetic (Story 55, found live):
    set_viewport_size alone leaves the request's User-Agent as desktop
    Chromium, and nora_home.ui.middleware.SurfaceMiddleware decides phone vs.
    desktop from the UA, never from viewport width — so without it, "iPhone"
    was testing the 228px-fixed-rail desktop shell squeezed to 390px, not the
    phone shell at all.
    """
    set_surface(signed_in, house_url, SURFACE_FOR_LABEL.get(label))
    signed_in.set_viewport_size({"width": width, "height": height})
    visit(signed_in, "/home/")

    overflow = signed_in.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")

    assert overflow <= 1, f"the home screen scrolls sideways on {label} by {overflow}px"
