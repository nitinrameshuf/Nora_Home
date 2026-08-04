"""
The two screens and the bus between them.

The recurring bug in this subsystem is not a crash — it is silence. The bus
relays anything; the browser ignores what it has no handler for; so a control
that does nothing looks exactly like a control that works. It has happened twice
(the kiosk's Dim/Wake buttons, and the notification banner). The first test group
below is the guard against a third time.
"""

from __future__ import annotations

import json
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.utils import timezone

from nora_home.displays.bus import ALL_DISPLAYS_GROUP, broadcast, group_for, send_to_display
from nora_home.displays.consumers import KIOSK_ACTIONS
from nora_home.displays.models import HEARTBEAT_GRACE_SECONDS, Display, DisplayCommand

pytestmark = pytest.mark.django_db

WALL_LIVE_JS = Path(settings.BASE_DIR) / "static" / "nora_home" / "js" / "wall-live.js"


# ── every command the kiosk may send must be implemented ─────────────────────

def _handled_message_types() -> set[str]:
    """The message types wall-live.js actually has a branch for. Parsed from the
    source rather than duplicated in a list here, so this cannot drift."""
    source = WALL_LIVE_JS.read_text()
    return set(re.findall(r'case\s+"([a-z_]+)"', source))


def test_the_wall_script_exists():
    assert WALL_LIVE_JS.exists(), f"{WALL_LIVE_JS} is missing"


def test_every_kiosk_action_has_a_handler_on_the_wall():
    """A kiosk button wired to an action the wall ignores is a dead control that
    looks alive. This is the regression guard for exactly that."""
    handled = _handled_message_types()

    unimplemented = {a for a in KIOSK_ACTIONS if a != "say"} - handled

    assert not unimplemented, (
        f"kiosk may send {sorted(unimplemented)}, but wall-live.js has no handler. "
        "Add the handler in the same commit as the action.")


def test_the_alert_banner_is_still_handled():
    """The notification `display` channel sends type=banner. It once sent it to
    a wall with no handler and no element, and the alert vanished silently with
    every layer reporting success."""
    assert "banner" in _handled_message_types()


def test_kiosk_actions_stay_a_short_allow_list():
    """Actions accumulate; handlers do not. Keeping the list tight is what stops
    the two drifting apart again."""
    assert KIOSK_ACTIONS == {"navigate", "refresh", "say"}


# ── the bus ──────────────────────────────────────────────────────────────────

def test_group_naming_is_stable():
    assert group_for("wall") == "display.wall"
    assert ALL_DISPLAYS_GROUP == "display.all"


def test_send_to_display_reaches_the_layer(wall_display):
    assert send_to_display("wall", {"type": "refresh"}) is True


def test_broadcast_reaches_the_layer():
    assert broadcast({"type": "refresh"}) is True


def test_a_missing_channel_layer_is_survivable(monkeypatch):
    """"The wall display must survive anything" (CLAUDE.md §6). A dead Redis
    should degrade the screen, not raise into whatever was pushing to it."""
    import nora_home.displays.bus as bus

    monkeypatch.setattr(bus, "get_channel_layer", lambda: None)

    assert send_to_display("wall", {"type": "refresh"}) is False


def test_a_layer_that_raises_is_survivable(monkeypatch):
    import nora_home.displays.bus as bus

    class Exploding:
        def group_send(self, *args, **kwargs):
            raise RuntimeError("redis is gone")

    monkeypatch.setattr(bus, "get_channel_layer", lambda: Exploding())

    assert send_to_display("wall", {"type": "refresh"}) is False


# ── display state ────────────────────────────────────────────────────────────

def test_a_display_that_never_checked_in_is_offline(wall_display):
    assert wall_display.last_seen_at is None
    assert wall_display.is_online is False


def test_a_recent_heartbeat_means_online(wall_display):
    wall_display.touch()
    wall_display.refresh_from_db()

    assert wall_display.is_online is True


def test_an_old_heartbeat_means_offline(wall_display):
    wall_display.last_seen_at = timezone.now() - timedelta(
        seconds=HEARTBEAT_GRACE_SECONDS + 10)
    wall_display.save()

    assert wall_display.is_online is False


def test_touch_does_not_disturb_anything_else(wall_display):
    """`touch()` runs on every heartbeat, twice a minute, forever. Writing the
    whole row each time would clobber a command applied in between."""
    wall_display.current_panel = "something"
    wall_display.save()

    wall_display.touch()

    wall_display.refresh_from_db()
    assert wall_display.current_panel == "something"


@pytest.mark.parametrize("hour,expected", [(23, True), (2, True), (6, False), (12, False)])
def test_night_mode_wraps_midnight(wall_display, monkeypatch, hour, expected):
    import nora_home.displays.models as models

    class FakeTz:
        @staticmethod
        def localtime():
            return timezone.localtime().replace(hour=hour)

        now = timezone.now

    monkeypatch.setattr(models, "timezone", FakeTz)

    assert wall_display.in_night_mode() is expected


def test_pinning_expires(wall_display):
    wall_display.pinned_until = timezone.now() - timedelta(minutes=1)
    assert wall_display.is_pinned is False

    wall_display.pinned_until = timezone.now() + timedelta(minutes=1)
    assert wall_display.is_pinned is True


def test_an_unpinned_display_is_not_pinned(wall_display):
    assert wall_display.is_pinned is False


# ── commands are auditable ───────────────────────────────────────────────────

def test_showing_a_panel_records_what_was_asked_and_by_whom(wall_display):
    """"Why did the wall show the grocery list at 2am" has to be answerable."""
    from nora_home.displays.bus import show_panel

    show_panel("wall", "tracker.WallAgendaPanel", pin_seconds=60, issued_by="kiosk")

    command = DisplayCommand.objects.get()
    assert command.action == "show"
    assert command.issued_by == "kiosk"
    assert command.payload["panel"] == "tracker.WallAgendaPanel"


def test_showing_a_panel_on_an_unknown_display_is_survivable():
    from nora_home.displays.bus import show_panel

    assert show_panel("garage", "some.Panel") is False


def test_showing_a_panel_on_an_inactive_display_is_refused(wall_display):
    from nora_home.displays.bus import show_panel

    wall_display.is_active = False
    wall_display.save()

    assert show_panel("wall", "some.Panel") is False


# ── the pages the physical screens load ──────────────────────────────────────

def test_the_wall_page_registers_its_display_row(client, adult):
    """Plugging in a new screen and opening the page should be all the setup
    there is — no admin step, no fixture."""
    client.force_login(adult)

    response = client.get("/home/displays/wall/")

    assert response.status_code == 200
    assert Display.objects.filter(slug=settings.NORA_HOME_MAIN_DISPLAY_SLUG).exists()


def test_the_wall_page_is_the_iframe_shell(client, adult):
    client.force_login(adult)

    response = client.get("/home/displays/wall/")

    assert b"<iframe" in response.content, "the wall is not serving the live shell"


def test_the_kiosk_page_renders(client, adult, kiosk_display):
    client.force_login(adult)

    assert client.get("/home/displays/kiosk/").status_code == 200


def test_the_kiosk_can_be_framed_but_the_wall_shell_is_same_origin(client, adult):
    """The wall iframes the real app from the same origin; X_FRAME_OPTIONS must
    permit that and nothing wider."""
    client.force_login(adult)

    response = client.get("/home/displays/kiosk/")

    assert response.headers.get("X-Frame-Options", "SAMEORIGIN") == "SAMEORIGIN"


def test_the_old_displays_page_redirects_to_settings(client, adult):
    """The Displays tab was folded into Settings; old links must still land."""
    client.force_login(adult)

    response = client.get("/home/displays/")

    assert response.status_code in (301, 302)
    assert "/home/settings/" in response.headers["Location"]


def test_display_pages_require_a_signed_in_member(client):
    response = client.get("/home/displays/kiosk/")

    assert response.status_code == 302
