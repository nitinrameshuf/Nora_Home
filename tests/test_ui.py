"""
Surface detection and the home bot.

Surface detection decides which CSS and which layout every request gets. It has
to be right for the two fixed-purpose screens in particular: if the 24" wall is
ever detected as "desktop", it renders at laptop scale and is unreadable from
three metres, and nobody is standing at it to notice.
"""

from __future__ import annotations

import pytest

from nora_home.ui import bot
from nora_home.ui.middleware import SurfaceMiddleware

IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1")
IPAD = ("Mozilla/5.0 (iPad; CPU OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Safari/604.1")
ANDROID_PHONE = ("Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 "
                 "(KHTML, like Gecko) Chrome/120.0 Mobile Safari/537.36")
ANDROID_TABLET = ("Mozilla/5.0 (Linux; Android 14; SM-X200) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
MAC = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
PI_KIOSK = ("Mozilla/5.0 (X11; Linux aarch64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")


def _surface(rf, path="/home/", agent="", cookies=None, **extra):
    request = rf.get(path, HTTP_USER_AGENT=agent, **extra)
    request.COOKIES.update(cookies or {})
    captured = {}

    def view(req):
        captured["surface"] = req.nh_surface
        captured["touch"] = req.nh_is_touch
        from django.http import HttpResponse
        return HttpResponse()

    response = SurfaceMiddleware(view)(request)
    captured["header"] = response["X-Nora-Surface"]
    return captured


# ── the two fixed screens ────────────────────────────────────────────────────

def test_the_wall_url_is_always_the_wall(rf):
    """Chromium on the Pi looks exactly like a desktop browser. Only the URL can
    tell the 24" apart — and getting it wrong makes it unreadable from across
    the room, with nobody standing there to notice."""
    assert _surface(rf, "/home/displays/wall/", PI_KIOSK)["surface"] == "wall"


def test_the_kiosk_url_is_always_the_kiosk(rf):
    assert _surface(rf, "/home/displays/kiosk/", PI_KIOSK)["surface"] == "kiosk"


def test_a_named_wall_is_still_the_wall(rf):
    assert _surface(rf, "/home/displays/wall/garage/", MAC)["surface"] == "wall"


def test_the_url_beats_a_cookie_override(rf):
    """Someone forcing 'phone' on their laptop must not be able to leave the
    physical wall stuck in phone layout."""
    surface = _surface(rf, "/home/displays/wall/", MAC, {"nh_surface": "phone"})

    assert surface["surface"] == "wall"


# ── the wall's own iframe (§11.1, "Wall Type Scale") ─────────────────────────
#
# The wall's shell page is at /home/displays/wall/, matched above by
# WALL_PREFIXES — but §11 wants the *real app content the shell iframes*
# (/home/, /todo/, …) at the same 1.6x scale, and that content is requested
# at its own ordinary URL with no "wall" in the path at all. These tests are
# the part of the surface story the URL-prefix check alone cannot cover.

def test_content_iframed_by_the_wall_is_also_the_wall(rf):
    surface = _surface(rf, "/home/", MAC, HTTP_SEC_FETCH_DEST="iframe",
                       HTTP_REFERER="https://nora.home/home/displays/wall/")

    assert surface["surface"] == "wall"


def test_the_same_page_opened_directly_is_not_the_wall(rf):
    """The one failure mode this whole mechanism exists to avoid: someone on
    their own laptop opening /home/ normally must never get wall-sized text."""
    surface = _surface(rf, "/home/", MAC)

    assert surface["surface"] == "desktop"


def test_an_iframe_from_somewhere_else_is_not_the_wall(rf):
    """Sec-Fetch-Dest alone is not enough — anything could iframe the app.
    Only a referer naming the wall's own page counts."""
    surface = _surface(rf, "/home/", MAC, HTTP_SEC_FETCH_DEST="iframe",
                       HTTP_REFERER="https://nora.home/some/other/page/")

    assert surface["surface"] == "desktop"


def test_a_named_walls_iframe_is_still_the_wall(rf):
    surface = _surface(rf, "/todo/", MAC, HTTP_SEC_FETCH_DEST="iframe",
                       HTTP_REFERER="https://nora.home/home/displays/wall/garage/")

    assert surface["surface"] == "wall"


# ── device detection ─────────────────────────────────────────────────────────

@pytest.mark.parametrize("agent,expected", [
    (IPHONE, "phone"),
    (ANDROID_PHONE, "phone"),
    (IPAD, "tablet"),
    (ANDROID_TABLET, "tablet"),
    (MAC, "desktop"),
    ("", "desktop"),
])
def test_devices_are_detected_from_the_user_agent(rf, agent, expected):
    assert _surface(rf, "/home/", agent)["surface"] == expected


def test_an_android_phone_is_not_mistaken_for_a_tablet(rf):
    """Android tablets and phones differ only by the word "Mobile"; the tablet
    pattern has to exclude it or every Android phone gets tablet layout."""
    assert _surface(rf, "/home/", ANDROID_PHONE)["surface"] == "phone"


# ── overrides ────────────────────────────────────────────────────────────────

def test_a_cookie_overrides_the_user_agent(rf):
    surface = _surface(rf, "/home/", MAC, {"nh_surface": "phone"})

    assert surface["surface"] == "phone"


def test_a_nonsense_cookie_is_ignored(rf):
    surface = _surface(rf, "/home/", MAC, {"nh_surface": "hologram"})

    assert surface["surface"] == "desktop"


# ── what the rest of the system reads ────────────────────────────────────────

@pytest.mark.parametrize("agent,touch", [
    (IPHONE, True), (IPAD, True), (MAC, False),
])
def test_touch_is_derived_from_the_surface(rf, agent, touch):
    assert _surface(rf, "/home/", agent)["touch"] is touch


def test_the_kiosk_is_a_touch_surface(rf):
    assert _surface(rf, "/home/displays/kiosk/", PI_KIOSK)["touch"] is True


def test_the_wall_is_not_a_touch_surface(rf):
    """The 24" has no touch panel at all — offering tap targets on it would be
    offering controls that cannot be used."""
    assert _surface(rf, "/home/displays/wall/", PI_KIOSK)["touch"] is False


def test_the_surface_is_echoed_in_a_response_header(rf):
    """Debugging a layout on a device you are not holding starts here."""
    assert _surface(rf, "/home/", IPHONE)["header"] == "phone"


# ── the home bot ─────────────────────────────────────────────────────────────

def test_say_pushes_a_message():
    assert bot.say("Three days on the trot.") is True


def test_an_unknown_mood_falls_back_rather_than_breaking(monkeypatch):
    sent = {}
    monkeypatch.setattr(bot, "_push", lambda payload: sent.update(payload) or True)

    bot.say("hello", mood="incandescent")

    assert sent["mood"] == "happy"


def test_a_known_mood_is_preserved(monkeypatch):
    sent = {}
    monkeypatch.setattr(bot, "_push", lambda payload: sent.update(payload) or True)

    bot.say("well done", mood="proud")

    assert sent["mood"] == "proud"


def test_a_long_line_is_truncated(monkeypatch):
    sent = {}
    monkeypatch.setattr(bot, "_push", lambda payload: sent.update(payload) or True)

    bot.say("x" * 1000)

    assert len(sent["message"]) == 280


def test_the_bot_survives_a_dead_channel_layer(monkeypatch):
    """The bot is decoration. It must never be able to break the page it is on."""
    monkeypatch.setattr(bot, "get_channel_layer", lambda: None)

    assert bot.say("hello") is False
    assert bot.react("happy") is False


def test_the_bot_survives_a_layer_that_raises(monkeypatch):
    class Exploding:
        def group_send(self, *args, **kwargs):
            raise RuntimeError("redis is gone")

    monkeypatch.setattr(bot, "get_channel_layer", lambda: Exploding())

    assert bot.say("hello") is False


@pytest.mark.django_db
def test_pushing_a_notification_carries_what_the_bell_needs(member):
    from nora_home.notifications.models import Notification

    notification = Notification.objects.create(
        title="Overdue", body="x", severity="warning", recipient=member,
        app_slug="todo")

    assert bot.push_notification(notification) is True


@pytest.mark.django_db
def test_pushing_a_house_notification_has_no_recipient(monkeypatch, db):
    from nora_home.notifications.models import Notification

    sent = {}
    monkeypatch.setattr(bot, "_push", lambda payload: sent.update(payload) or True)
    notification = Notification.objects.create(title="Power cut", app_slug="core")

    bot.push_notification(notification)

    assert sent["recipient"] is None


def test_the_bot_message_type_matches_its_consumer():
    """Channels turns a dotted type into an underscored method name. If these
    drift, every message is silently dropped by the consumer."""
    from nora_home.ui.consumers import HomeBotConsumer

    expected_method = bot.BOT_MESSAGE_TYPE.replace(".", "_")

    assert hasattr(HomeBotConsumer, expected_method), (
        f"HomeBotConsumer has no {expected_method}() for type {bot.BOT_MESSAGE_TYPE!r}")


# ── the wall's type scale, and what it silently depends on ───────────────────
#
# `html[data-surface="wall"] { font-size: N% }` only works because *everything
# else* is rem. Anything sized in px keeps its laptop size while the text around
# it grows, and the result is not "slightly off" — it clips. This has now been
# found twice on the real 24" (Gridstack's cellHeight: 80, then --nav-width:
# 244px cutting "Measurements" mid-word), both times by looking at the physical
# screen rather than at the diff, because no unit test could see a browser
# layout. These read the stylesheet as text, which is the part a test *can* see.

def _stylesheet() -> str:
    from pathlib import Path

    from django.conf import settings

    css = Path(settings.BASE_DIR) / "static" / "nora_home" / "css" / "nora-home.css"
    return css.read_text(encoding="utf-8")


def test_the_wall_scales_with_its_viewport_not_a_fixed_number():
    """`vw`, so the same physical wall stays legible at a different resolution.
    A bare percentage here would be pinned to this house's 1080p panel."""
    import re

    match = re.search(
        r'html\[data-surface="wall"\]\s*\{\s*font-size:\s*clamp\(\s*'
        r'(\d+(?:\.\d+)?)px\s*,\s*(\d+(?:\.\d+)?)vw\s*,\s*(\d+(?:\.\d+)?)px\s*\)',
        _stylesheet())

    assert match, "the wall's root font-size is no longer a clamped vw scale"
    floor, vw, ceiling = (float(g) for g in match.groups())

    # The clamp is the guard rail: an odd display must not be able to make the
    # house unreadable in either direction.
    assert 16 <= floor < ceiling <= 32, f"clamp bounds {floor}-{ceiling}px are wrong"

    # And at the wall this house actually has, it must land where it was
    # measured. 1.125vw on 1920 is 21.6px — the 135% that read correctly from
    # three metres once the sidebar stopped clipping.
    at_1920 = vw / 100 * 1920
    assert floor <= at_1920 <= ceiling, "the clamp excludes this house's own wall"
    assert 20 <= at_1920 <= 23, (
        f"{vw}vw resolves to {at_1920}px on the 24\" wall; 21.6px was what "
        f"measured right on the real screen")


@pytest.mark.parametrize("token", ["--nav-width", "--tap"])
def test_layout_tokens_are_rem_so_the_wall_scale_reaches_them(token):
    """A px value here is the bug that clipped the sidebar. Both of these size
    boxes that hold text, so both have to grow when the text does."""
    import re

    match = re.search(rf"{token}:\s*([^;]+);", _stylesheet())

    assert match, f"{token} is no longer defined"
    value = match.group(1).strip()
    assert value.endswith("rem"), (
        f"{token} is {value!r} — a fixed pixel size does not follow the wall's "
        f"root font-size, so its box stays laptop-sized while its contents grow")


def test_the_card_grid_minimum_is_rem_not_px():
    """`minmax(280px, 1fr)` would hold cards at laptop width on the wall while
    their contents ran larger inside them."""
    assert "minmax(17.5rem, 1fr)" in _stylesheet(), (
        "the card grid's minimum column width must be rem — see --nav-width")
