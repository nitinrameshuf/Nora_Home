"""
QA tests: a real browser, against a running house.

These are the layer the fast suite cannot reach. `tests/` checks Python — rules,
the database, whether a URL returns 200. It never renders a page, never runs a
line of the 1,381 lines of JavaScript that ship to browsers, and never looks at
a pixel. Every user-visible bug found in the 2026-08-04 sessions lived in that
gap and was caught by screenshotting the Pi by hand:

  * "Add a widget" silently doing nothing (a JS global was overwritten)
  * alert banners never appearing on the wall (no handler for the message)
  * the kiosk showing buttons that had been deleted days earlier
  * text on the dark theme nobody could read

The fast suite was green through all of it. This suite is the automated version
of that manual loop.

Deliberately **not** part of `./nora test`:

  * it needs a running house, which unit tests must never need;
  * it takes minutes rather than seconds;
  * a browser is flakier than a function call, and a fast suite people trust is
    worth more than a slow one they learn to re-run.

Run it with `./nora qa`, which points it at the Pi by default.
"""

from __future__ import annotations

import os

import pytest
import requests
import urllib3

# The house serves a self-signed cert (no public domain on a LAN — see
# CLAUDE.md §4), so the warning is expected and would otherwise drown the output.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

DEFAULT_URL = "https://192.168.1.253"


def pytest_addoption(parser):
    parser.addoption("--house-url", action="store", default=None,
                     help="The running house to test against.")


@pytest.fixture(scope="session")
def house_url(request) -> str:
    return (request.config.getoption("--house-url")
            or os.environ.get("NORA_HOME_QA_URL")
            or DEFAULT_URL).rstrip("/")


@pytest.fixture(scope="session", autouse=True)
def house_is_up(house_url):
    """Fail fast and legibly. A browser timing out 40 times is a much worse way
    to learn the house is down."""
    try:
        response = requests.get(f"{house_url}/home/health/", verify=False, timeout=10)
    except requests.RequestException as exc:
        pytest.skip(f"No house at {house_url} ({exc.__class__.__name__}). "
                    f"Start it with ./nora up, or pass --house-url.")
    if response.status_code >= 500:
        pytest.skip(f"The house at {house_url} is unhealthy (HTTP {response.status_code}).")


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args, house_url):
    return {
        **browser_context_args,
        "base_url": house_url,
        "ignore_https_errors": True,   # self-signed, by design
        "viewport": {"width": 1400, "height": 900},
    }


@pytest.fixture
def console_errors(page):
    """Collect anything the browser complained about.

    This is the cheapest high-value check in the whole file. "Add a widget" broke
    for a day looking perfectly fine — the POST 403'd, and because `fetch()` does
    not reject on a non-2xx the page reloaded anyway. The only visible trace was
    in the console, where nothing was watching.
    """
    errors: list[str] = []
    page.on("console", lambda m: errors.append(f"{m.type}: {m.text}")
            if m.type == "error" else None)
    page.on("pageerror", lambda e: errors.append(f"uncaught: {e}"))
    return errors


def visit(page, path: str):
    """Go to a page and wait for it to settle.

    Deliberately **not** `networkidle`. The wall and the kiosk hold a websocket
    open for their whole life and poll the weather endpoint every few minutes,
    so the network is never idle and the wait times out after 30s — which is
    what made the first run of this suite take five and a half minutes and
    report failures that were nothing but my own wait condition.
    """
    page.goto(path, wait_until="domcontentloaded")
    page.wait_for_load_state("load")
    page.wait_for_timeout(600)   # let deferred scripts run and lay out
    return page


def open_actions_menu(page):
    """Open the profile dropdown.

    Page actions — "Add a widget", "Rearrange", the household switcher — live
    inside it (`{% block actions %}` renders into `.profile-dropdown` in
    base.html), so they are present in the DOM but not visible until it is
    opened. Worth knowing before concluding a button is broken.
    """
    trigger = page.locator(".profile-trigger").first
    if trigger.count() == 0:
        pytest.skip("no profile menu on this surface")
    trigger.click()
    page.wait_for_timeout(250)
    return page


@pytest.fixture
def signed_in(page, house_url):
    """A page signed in as the first household member.

    There is no password anywhere in this house (CLAUDE.md §4) — the switcher is
    the front door, so signing in is a click.
    """
    visit(page, f"{house_url}/accounts/switch/")
    buttons = page.locator("form button[type=submit]")
    if buttons.count() == 0:
        pytest.skip("No household members exist — run: ./nora member <you> admin")
    buttons.first.click()
    page.wait_for_load_state("load")
    return page


# Pages every household member can reach. Kept here rather than in each test so
# a new platform page gets smoke-tested by adding one line.
PLATFORM_PAGES = [
    ("home", "/home/"),
    ("apps", "/home/apps/"),
    ("status", "/home/system/"),
    ("settings", "/home/settings/"),
    ("household", "/accounts/household/"),
    ("tracker", "/home/tracker/"),
    ("alerts", "/home/alerts/"),
    ("measurements", "/home/measurements/"),
    ("integrations", "/home/integrations/"),
    ("assistant", "/home/ai/"),
]

SCREEN_PAGES = [
    ("wall", "/home/displays/wall/"),
    ("kiosk", "/home/displays/kiosk/"),
]


# ── contrast, measured from pixels ────────────────────────────────────────────
#
# axe's own colour-contrast rule is unusable on this app, and it took a pixel
# measurement to establish that rather than assume it. axe walks the DOM to find
# an opaque ancestor and composites the translucent panes onto it — but the
# living background is a fixed gradient painted behind everything, with
# `backdrop-filter` on top. So axe reported the kiosk tiles as 1.95:1 against a
# background colour of #b4b5b6, a light grey that appears nowhere on screen.
# Measured from the actual rendered pixels, the same text is 6.49:1 — which
# passes comfortably.
#
# Taking axe at its word would have meant "fixing" readable text and making it
# worse. So contrast is measured here instead, from a screenshot, which is the
# only thing that knows what the compositor actually drew. Every other axe rule
# is left switched on: they read the DOM, which axe is good at.

WCAG_AA_NORMAL = 4.5
WCAG_AA_LARGE = 3.0


def _relative_luminance(colour) -> float:
    def channel(value: int) -> float:
        srgb = value / 255
        return srgb / 12.92 if srgb <= 0.03928 else ((srgb + 0.055) / 1.055) ** 2.4

    red, green, blue = colour[:3]
    return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue)


def contrast_ratio(one, two) -> float:
    first, second = _relative_luminance(one), _relative_luminance(two)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def measure_text_contrast(page, selector: str, index: int = 0) -> float | None:
    """Contrast between the glyphs and their background, as actually drawn.

    Screenshots the element and treats the most common colour as the background
    and the pixel furthest from it in luminance as the glyph. Antialiasing puts
    plenty of in-between pixels in the box, but the extremes are what a person
    reads. Returns None when the element is missing or too small to judge.
    """
    from collections import Counter
    from io import BytesIO

    from PIL import Image

    element = page.locator(selector).nth(index)
    if element.count() == 0 or not element.is_visible():
        return None
    box = element.bounding_box()
    if not box or box["width"] < 4 or box["height"] < 4:
        return None

    image = Image.open(BytesIO(page.screenshot(clip=box))).convert("RGB")
    # getdata() is deprecated in Pillow 14; list(image) would give rows.
    pixels = list(image.convert("RGB").tobytes())
    pixels = [tuple(pixels[i:i + 3]) for i in range(0, len(pixels), 3)]
    if len(pixels) < 16:
        return None

    background = Counter(pixels).most_common(1)[0][0]
    glyph = max(pixels, key=lambda p: abs(_relative_luminance(p)
                                          - _relative_luminance(background)))
    return contrast_ratio(glyph, background)
