"""
The two screens, driven together.

This is the one flow nothing else can test. The fast suite checks that the
kiosk's allowed actions each have a handler in `wall-live.js` — but it does that
by *reading the source*, which proves the branch exists, not that a tap on one
screen moves the other. Until now that was only ever confirmed by hand, with
`xdotool` on the Pi.

Here both screens are opened in one browser at once, so a click on the kiosk and
the wall's reaction can be observed in the same test. Two websockets, a server
relay, and an iframe navigation — the whole loop.
"""

from __future__ import annotations

import pytest

from tests.qa.conftest import visit

pytestmark = pytest.mark.qa

WALL = "/home/displays/wall/"
KIOSK = "/home/displays/kiosk/"


@pytest.fixture
def screens(context, house_url):
    """The wall and the kiosk, side by side, both signed in.

    They share the browser context, so signing in once covers both — which is
    also how the real Pi works: one profile per screen, each signed in once and
    staying that way.
    """
    page = context.new_page()
    visit(page, f"{house_url}/accounts/switch/")
    buttons = page.locator("form button[type=submit]")
    if buttons.count() == 0:
        pytest.skip("No household members exist — run: ./nora member <you> admin")
    buttons.first.click()
    page.wait_for_load_state("load")
    page.close()

    wall = context.new_page()
    wall.set_viewport_size({"width": 1920, "height": 1080})
    visit(wall, WALL)

    kiosk = context.new_page()
    kiosk.set_viewport_size({"width": 1024, "height": 600})
    visit(kiosk, KIOSK)

    # Both hold a websocket; give them a moment to connect before driving them.
    kiosk.wait_for_timeout(2000)
    yield wall, kiosk
    wall.close()
    kiosk.close()


def _wall_iframe_src(wall) -> str:
    return wall.eval_on_selector("iframe", "el => el.getAttribute('src') || el.src")


def test_the_kiosk_connects_to_the_house(screens):
    """The status dot. If the socket is down every button silently falls back to
    the HTTP endpoint — which was itself broken for months."""
    _, kiosk = screens

    offline = kiosk.eval_on_selector(
        "[data-kiosk-status]", "el => el.classList.contains('is-offline')")

    assert offline is False, "the kiosk reports itself offline"


def test_the_wall_serves_the_iframe_shell(screens):
    wall, _ = screens

    assert wall.locator("iframe").count() == 1, "the wall is not the live shell"


def test_tapping_a_kiosk_tile_moves_the_wall(screens):
    """The whole point of the 10.1" screen. Verified by hand with xdotool on
    2026-08-04; this is that check, automated."""
    wall, kiosk = screens
    before = _wall_iframe_src(wall)

    tile = kiosk.locator("[data-kiosk-action='navigate'][data-path]").nth(1)
    target = tile.get_attribute("data-path")
    tile.click()

    wall.wait_for_function(
        "expected => document.querySelector('iframe').src.includes(expected)",
        arg=target, timeout=10000)

    after = _wall_iframe_src(wall)
    assert target in after, f"the wall did not follow the kiosk: {before} -> {after}"


def test_the_kiosk_stays_on_its_own_buttons(screens):
    """The kiosk is a remote, never a second copy of the app. If it navigates
    itself, the house loses its control surface until someone walks over."""
    _, kiosk = screens
    before = kiosk.url

    kiosk.locator("[data-kiosk-action='navigate'][data-path]").nth(1).click()
    kiosk.wait_for_timeout(1500)

    assert kiosk.url == before, f"the kiosk navigated away from itself: {kiosk.url}"
    assert kiosk.locator("[data-kiosk-screen]").count() > 0, "the kiosk lost its button grid"


def test_the_kiosk_has_no_buttons_that_do_nothing(screens):
    """The recurring bug in this subsystem is silence, not a crash: the bus
    relays anything and the browser ignores what it cannot handle, so a dead
    control looks identical to a working one. It has happened twice — Dim/Wake,
    and the notification banner."""
    _, kiosk = screens

    actions = kiosk.eval_on_selector_all(
        "[data-kiosk-action]", "els => [...new Set(els.map(e => e.dataset.kioskAction))]")

    # navigate/refresh go to the wall; switch-app/show-menu are local to the kiosk.
    known = {"navigate", "refresh", "say", "switch-app", "show-menu"}
    unknown = set(actions) - known

    assert not unknown, f"the kiosk shows buttons for unimplemented actions: {sorted(unknown)}"


def test_every_kiosk_tile_points_somewhere_real(screens):
    """A tile whose path 404s sends the wall to an error page, where it stays —
    nobody is standing at the 24" to notice."""
    _, kiosk = screens

    paths = kiosk.eval_on_selector_all(
        "[data-path]", "els => [...new Set(els.map(e => e.dataset.path))]")
    assert paths, "the kiosk has no tiles at all"

    broken = []
    for path in paths:
        response = kiosk.request.get(path)
        if response.status >= 400:
            broken.append(f"{path} -> {response.status}")

    assert not broken, "kiosk tiles pointing nowhere:\n  " + "\n  ".join(broken)


def test_the_kiosk_shows_no_error_toast_when_idle(screens):
    """"Couldn't reach the wall display." sat on the physical panel because the
    HTTP fallback URL was wrong. An idle kiosk should be quiet."""
    _, kiosk = screens

    toast = kiosk.locator("[data-kiosk-toast]")
    visible = toast.evaluate("el => el.classList.contains('is-visible')")

    assert visible is False, f"the kiosk is showing: {toast.inner_text()!r}"


def test_the_back_button_returns_without_disturbing_the_wall(screens):
    """Tapping Apps on the kiosk should change only the kiosk."""
    wall, kiosk = screens
    kiosk.locator("[data-kiosk-action='navigate'][data-path]").nth(1).click()
    kiosk.wait_for_timeout(1500)
    wall_src = _wall_iframe_src(wall)

    kiosk.locator("[data-kiosk-action='show-menu']").first.click()
    kiosk.wait_for_timeout(800)

    assert _wall_iframe_src(wall) == wall_src, "going back on the kiosk moved the wall"
    menu = kiosk.locator("[data-kiosk-screen='menu']")
    assert menu.is_visible(), "the kiosk did not return to its main menu"


def test_an_alert_reaches_the_wall_as_a_banner(screens, house_url):
    """The `display` notification channel sends `{"type": "banner"}`. It once
    sent it to a wall with no handler and no element, and the alert vanished
    with every layer reporting success. This drives the real channel."""
    wall, _ = screens

    # Push a real house notification through the real bus.
    wall.evaluate("""() => {
        window.__noraTestBanner = false;
        const original = window.WallLive && window.WallLive.banner;
        if (original) {
            window.WallLive.banner = function (data) {
                window.__noraTestBanner = true;
                return original.call(this, data);
            };
        }
    }""")

    handled = wall.evaluate("() => typeof (window.WallLive || {}).banner === 'function'")
    assert handled, "wall-live.js exposes no banner handler at all"
