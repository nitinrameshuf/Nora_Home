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
from nora_home.displays.models import HEARTBEAT_GRACE_SECONDS, Display

pytestmark = pytest.mark.django_db

WALL_LIVE_JS = Path(settings.BASE_DIR) / "static" / "nora_home" / "js" / "wall-live.js"
KIOSK_JS = Path(settings.BASE_DIR) / "static" / "nora_home" / "js" / "kiosk.js"


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


# ── the command endpoint tells the truth ────────────────────────────────────

def test_the_command_endpoint_relays_a_navigate(client, adult, wall_display):
    client.force_login(adult)

    response = client.post(f"/home/displays/command/{wall_display.slug}/",
                           {"action": "navigate", "path": "/home/"})

    assert response.status_code == 200
    assert response.json()["ok"] is True


def test_the_command_endpoint_records_nothing_it_cannot_do(client, adult,
                                                           wall_display):
    """It used to accept show/pin/unpin/wake/sleep/next/previous — all left over
    from the ambient wall. The server relayed them, the wall ignored every one,
    and the caller got {"ok": true} for a command that did nothing."""
    client.force_login(adult)

    for dead in ["show", "pin", "unpin", "wake", "sleep", "next", "previous"]:
        response = client.post(f"/home/displays/command/{wall_display.slug}/",
                               {"action": dead})
        assert response.status_code == 400, f"{dead!r} is still accepted"
        assert response.json()["ok"] is False


def test_the_command_endpoint_accepts_exactly_the_kiosk_actions(client, adult,
                                                                wall_display):
    client.force_login(adult)

    for action in KIOSK_ACTIONS:
        response = client.post(f"/home/displays/command/{wall_display.slug}/",
                               {"action": action, "path": "/home/"})
        assert response.status_code == 200, f"{action!r} should be accepted"


def test_the_command_endpoint_404s_for_an_unknown_display(client, adult):
    client.force_login(adult)

    response = client.post("/home/displays/command/garage/", {"action": "refresh"})

    assert response.status_code == 404


def test_the_command_endpoint_requires_post(client, adult, wall_display):
    client.force_login(adult)

    assert client.get(f"/home/displays/command/{wall_display.slug}/").status_code == 405


def test_the_kiosks_http_fallback_url_actually_resolves():
    """kiosk.js falls back to this endpoint when the websocket is down. It
    posted to /displays/<slug>/command/ for as long as it existed — missing the
    /home/ prefix the platform is mounted under — so every fallback 404'd and
    surfaced on the panel as "Couldn't reach the wall display."."""
    from django.urls import resolve

    source = KIOSK_JS.read_text()
    # Rebuild the concatenated URL expression: take the whole first argument to
    # post(), keep its string literals, and substitute a real slug for the
    # variable pieces.
    calls = re.findall(r"NoraHome\.post\((.+?),\s*payload\)", source, re.S)

    assert calls, "kiosk.js no longer posts anywhere; update this test"
    for call in calls:
        concrete = "".join(re.findall(r'"([^"]*)"', call))
        concrete = concrete.replace("//", "/wall/") if "//" in concrete else concrete
        match = resolve(concrete)
        # Asserting it merely resolves is not enough: the old broken URL
        # (/home/displays/wall/command/) resolved perfectly well — to
        # wall_named(slug="command"), which renders the wall page in response to
        # a command. It has to reach the command view specifically.
        assert match.url_name == "command", (
            f"kiosk.js posts to {concrete}, which resolves to "
            f"{match.url_name!r}, not the command endpoint")


def test_the_status_endpoint_reports_only_live_fields(client, adult, wall_display):
    """panel and pinned belonged to the rotating ambient wall; nothing sets them
    now, so reporting them was reporting fiction."""
    client.force_login(adult)

    payload = client.get("/home/displays/status/").json()

    assert payload["displays"], "no displays reported"
    for entry in payload["displays"]:
        assert set(entry) == {"slug", "name", "kind", "online", "last_seen"}


# ── the retired ambient wall is really gone ─────────────────────────────────

def test_the_ambient_wall_files_are_removed():
    """wall.html and wall.js drove the pre-rendered rotating panels. Nothing
    rendered them after the iframe wall replaced them, so they sat as
    scaffolding that read like a live alternative."""
    base = Path(settings.BASE_DIR)

    assert not (base / "templates" / "displays" / "wall.html").exists()
    assert not (base / "static" / "nora_home" / "js" / "wall.js").exists()


def test_no_template_or_script_still_references_the_ambient_wall():
    base = Path(settings.BASE_DIR)
    offenders = []

    for folder in ["templates", "static/nora_home/js", "nora_home"]:
        for path in (base / folder).rglob("*"):
            if path.suffix not in {".html", ".js", ".py"} or "vendor" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            if "js/wall.js" in text or "displays/wall.html" in text:
                offenders.append(str(path.relative_to(base)))

    assert not offenders, f"still referencing the removed ambient wall: {offenders}"


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
