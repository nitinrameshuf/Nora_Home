"""
Every page, opened in a real browser.

The fast suite already asserts these URLs return 200. What it cannot see is what
happens *after* the HTML arrives: scripts that throw, requests that 404, a page
that renders blank because a global went missing. This is that half.
"""

from __future__ import annotations

import pytest

from tests.qa.conftest import PLATFORM_PAGES, SCREEN_PAGES, visit

pytestmark = pytest.mark.qa

ALL_PAGES = PLATFORM_PAGES + SCREEN_PAGES


@pytest.mark.parametrize("name,path", ALL_PAGES, ids=[n for n, _ in ALL_PAGES])
def test_page_loads_without_javascript_errors(signed_in, console_errors, name, path):
    """The check that would have caught "Add a widget" being broken for a day.

    It looked fine: the button was there, the page reloaded. The POST 403'd, but
    `fetch()` does not reject on a non-2xx, so nothing surfaced except a console
    error nobody was watching.
    """
    visit(signed_in, path)

    assert not console_errors, (
        f"{name} ({path}) logged browser errors:\n  " + "\n  ".join(console_errors))


@pytest.mark.parametrize("name,path", ALL_PAGES, ids=[n for n, _ in ALL_PAGES])
def test_page_makes_no_failed_requests(signed_in, name, path):
    """A 404 on a stylesheet or a script is invisible in the HTML and obvious on
    screen. The steady /favicon.ico 404s are a known, accepted gap."""
    failures: list[str] = []
    signed_in.on("response", lambda r: failures.append(f"{r.status} {r.url}")
                 if r.status >= 400 and "favicon" not in r.url else None)

    visit(signed_in, path)

    assert not failures, f"{name} ({path}) made failing requests:\n  " + "\n  ".join(failures)


@pytest.mark.parametrize("name,path", PLATFORM_PAGES, ids=[n for n, _ in PLATFORM_PAGES])
def test_page_actually_renders_something(signed_in, name, path):
    """A page can return 200 and be blank — a template that swallowed an
    exception, or CSS that hid everything. Assert there is visible text."""
    visit(signed_in, path)

    body_text = signed_in.locator("body").inner_text().strip()

    assert len(body_text) > 40, f"{name} ({path}) rendered almost nothing: {body_text!r}"


@pytest.mark.parametrize("name,path", ALL_PAGES, ids=[n for n, _ in ALL_PAGES])
def test_page_has_no_unrendered_template_syntax(signed_in, name, path):
    """Django's `{# #}` is single-line only; a multi-line one renders as visible
    text on the page. That has shipped in this project before."""
    visit(signed_in, path)

    body_text = signed_in.locator("body").inner_text()

    for leak in ["{%", "{{", "{#"]:
        assert leak not in body_text, f"{name} ({path}) shows raw template syntax {leak}"


@pytest.mark.parametrize("name,path", PLATFORM_PAGES, ids=[n for n, _ in PLATFORM_PAGES])
def test_page_does_not_scroll_sideways(signed_in, name, path):
    """Horizontal scroll is the classic responsive break, and on the wall — which
    nobody touches — it just means content is permanently off-screen."""
    visit(signed_in, path)

    overflow = signed_in.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")

    assert overflow <= 1, f"{name} ({path}) scrolls sideways by {overflow}px"


def test_the_platform_javascript_actually_loaded(signed_in):
    """`nh-bot.js` once did `window.NoraHome = NoraHome`, wiping `csrfToken()`
    and `post()` that `nh-app.js` had put there — which is what broke "Add a
    widget". Every later script assumes those exist."""
    visit(signed_in, "/home/")

    missing = signed_in.evaluate("""() => {
        const api = window.NoraHome || {};
        return ['csrfToken', 'post', 'say'].filter(k => typeof api[k] !== 'function');
    }""")

    assert not missing, f"window.NoraHome is missing: {missing}"


def test_signing_in_needs_no_password(page, house_url):
    """The whole access model: tap a name, you are them. If this ever grows a
    password field, the wall and kiosk stop being able to sign themselves in."""
    visit(page, f"{house_url}/accounts/switch/")

    assert page.locator("input[type=password]").count() == 0, (
        "the switcher has grown a password field")
