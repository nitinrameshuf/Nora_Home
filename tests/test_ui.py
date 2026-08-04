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


def _surface(rf, path="/home/", agent="", cookies=None):
    request = rf.get(path, HTTP_USER_AGENT=agent)
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
        app_slug="tracker")

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
