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
from nora_home.displays.consumers import KIOSK_ACTIONS, KioskConsumer
from nora_home.displays.models import HEARTBEAT_GRACE_SECONDS, Display

pytestmark = pytest.mark.django_db

# assets/, not static/: since Story 43 these are Vite's input. Its output is
# hashed and minified, which is no use to a test that reads the source.
WALL_LIVE_JS = Path(settings.BASE_DIR) / "assets" / "js" / "wall-live.js"
KIOSK_JS = Path(settings.BASE_DIR) / "assets" / "js" / "kiosk.js"


# ── every command the kiosk may send must be implemented ─────────────────────

def _handled_message_types() -> set[str]:
    """The message types wall-live.js actually has a branch for. Parsed from the
    source rather than duplicated in a list here, so this cannot drift."""
    source = WALL_LIVE_JS.read_text()
    return set(re.findall(r'case\s+"([a-z_]+)"', source))


def test_the_wall_script_exists():
    assert WALL_LIVE_JS.exists(), f"{WALL_LIVE_JS} is missing"


def test_every_relayed_kiosk_action_has_a_handler_on_the_wall():
    """A kiosk button wired to an action the wall ignores is a dead control that
    looks alive. This is the regression guard for exactly that.

    SERVER_SIDE_ACTIONS are exempt because they are never relayed: `zoom`
    writes a house setting in the consumer and turns into a `refresh`, so the
    wall having no `case "zoom"` is correct rather than a missing handler."""
    from nora_home.displays.consumers import SERVER_SIDE_ACTIONS

    handled = _handled_message_types()

    relayed = {a for a in KIOSK_ACTIONS if a != "say"} - SERVER_SIDE_ACTIONS
    unimplemented = relayed - handled

    assert not unimplemented, (
        f"kiosk may send {sorted(unimplemented)}, but wall-live.js has no handler. "
        "Add the handler in the same commit as the action.")


def test_a_server_side_action_is_never_also_relayed():
    """The exemption above is only safe while those actions really are handled
    in the consumer. One that slipped back into the relay path would reach a
    wall with no handler and silently do nothing — the exact failure the
    allow-list exists to prevent."""
    from nora_home.displays.consumers import SERVER_SIDE_ACTIONS

    source = (Path(settings.BASE_DIR) / "nora_home" / "displays" / "consumers.py").read_text()

    for action in SERVER_SIDE_ACTIONS:
        assert f'action == "{action}"' in source, (
            f"{action} is exempt from the wall-handler rule but the consumer "
            "has no branch for it — it would be relayed to a wall that ignores it")


def test_the_alert_banner_is_still_handled():
    """The notification `display` channel sends type=banner. It once sent it to
    a wall with no handler and no element, and the alert vanished silently with
    every layer reporting success."""
    assert "banner" in _handled_message_types()


def test_kiosk_actions_stay_a_short_allow_list():
    """Actions accumulate; handlers do not. Keeping the list tight is what stops
    the two drifting apart again."""
    assert KIOSK_ACTIONS == {"navigate", "refresh", "say", "scroll", "zoom"}


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
    whole row each time would clobber an edit made in between."""
    wall_display.location = "living room"
    wall_display.save()

    wall_display.touch()

    wall_display.refresh_from_db()
    assert wall_display.location == "living room"


@pytest.mark.parametrize("field", [
    "current_panel", "rotation_enabled", "rotation_seconds", "pinned_until",
    "night_mode_start", "night_mode_end", "brightness",
])
def test_the_ambient_walls_fields_are_gone(field):
    """These described a rotating pre-rendered wall that no longer exists. They
    were kept "in case a passive view is wanted again" and turned into a trap:
    admin columns and a websocket payload reporting values nothing set and
    nothing read."""
    assert not hasattr(Display, field), f"Display.{field} is back"


def test_the_connect_payload_carries_only_what_the_wall_reads():
    """The payload used to include panel/rotation/night_mode. wall-live.js has
    never read any of it."""
    import inspect

    from nora_home.displays import consumers

    source = inspect.getsource(consumers.DisplayConsumer)

    for gone in ["current_panel", "rotation_enabled", "in_night_mode"]:
        assert gone not in source, f"the connect payload still sends {gone}"


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
    assert not (base / "assets" / "js" / "wall.js").exists()


def test_no_template_or_script_still_references_the_ambient_wall():
    base = Path(settings.BASE_DIR)
    offenders = []

    for folder in ["templates", "assets/js", "nora_home"]:
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


# ── the control desk (Story 50) ───────────────────────────────────────────────

def test_the_desk_offers_home_and_every_nav_app(client, adult, kiosk_display):
    """The app scroller is grounded in the registry, so installing an app puts
    it on the desk with no platform change. Home is not a nav app — it is the
    base platform — so it is named explicitly and must still be there."""
    from nora_home.core.registry import wall_apps

    client.force_login(adult)
    body = client.get("/home/displays/kiosk/").content.decode()

    for app in wall_apps("adult"):
        assert f'data-desk-bank="{app["slug"]}"' in body, f"{app['slug']} has no key bank"
    assert 'data-v="home"' in body


def test_every_app_on_the_desk_has_at_least_one_key(client, adult, kiosk_display):
    """An app that declares no nora_kiosk_controls still gets one key. An empty
    bank reads as a broken panel, not as "this app has one destination"."""
    from nora_home.core.registry import wall_apps

    for app in wall_apps("adult"):
        assert app["controls"], f"{app['slug']} would render an empty bank"


def test_every_key_on_the_desk_is_a_path_that_resolves(client, adult, kiosk_display):
    """Every key is a path the wall navigates to, because navigate/refresh/
    banner is the whole vocabulary wall-live.js implements. A key pointing at
    a URL that 404s is a dead control that looks alive."""
    from nora_home.core.registry import wall_apps

    client.force_login(adult)

    for app in wall_apps("adult"):
        for control in app["controls"]:
            assert client.get(control["path"]).status_code == 200, (
                f"{app['slug']} key {control['title']!r} -> {control['path']} is broken")


def test_the_controls_with_no_capability_behind_them_are_rendered_dead(
        client, adult, kiosk_display):
    """A control that moves and changes nothing is the "dead button with no
    error anywhere" this project warns about, so anything the platform cannot
    actually drive must be inert and visibly unlit.

    Story 51 made zoom and the scroll wheel live. Volume and wall power are
    still dead, and for different reasons worth keeping straight: volume needs
    a host mixer call the container cannot make, and wall-only power has no
    working mechanism on this hardware at all — four were tested and every one
    was disproved or blocked (docs/Main_App/progress.md)."""
    import re

    client.force_login(adult)
    body = client.get("/home/displays/kiosk/").content.decode()

    assert "is-dead" in body, "nothing is marked dead, but volume and power still are"
    # Whatever is dead must be genuinely inert, not merely dimmed.
    for block in re.findall(r"<button[^>]*is-dead[^>]*>", body):
        assert "data-kiosk-action" not in block, (
            f"a dead control carries a live action: {block}")
        assert "disabled" in block, f"a dead control is not disabled: {block}"


def test_zoom_and_scroll_are_live_on_the_desk(client, adult, kiosk_display):
    """The other half of the same guarantee: Story 51's two solved
    capabilities must actually be wired, not still drawn dead."""
    client.force_login(adult)
    body = client.get("/home/displays/kiosk/").content.decode()

    assert 'data-kiosk-action="zoom"' in body, "the zoom fader is not wired"
    assert "data-desk-bend" in body, "the scroll wheel is not wired"
    assert 'class="pbend is-dead"' not in body


def test_the_desk_never_sends_an_action_the_wall_cannot_handle(client, adult, kiosk_display):
    """The same guarantee test_every_kiosk_action_has_a_handler_on_the_wall
    makes about the allow-list, asserted against the rendered panel — every
    data-kiosk-action actually on the desk must be one wall-live.js implements."""
    import re

    client.force_login(adult)
    body = client.get("/home/displays/kiosk/").content.decode()

    on_the_panel = set(re.findall(r'data-kiosk-action="([a-z-]+)"', body))

    assert on_the_panel, "the desk has no live controls at all"
    assert on_the_panel <= KIOSK_ACTIONS, (
        f"the desk sends {sorted(on_the_panel - KIOSK_ACTIONS)}, which the wall "
        "does not implement")


def test_the_kiosk_reloads_itself_when_the_bus_says_refresh():
    """`./nora screens` broadcasts {type:"refresh"} to every connected screen
    after a deploy, and `nora`'s own comment claimed both screens honoured it.
    wall-live.js always did; kiosk.js never had the branch, so the kiosk
    silently kept its old markup — found on the physical panel deploying Story
    47, where it held an eight-tile render containing a since-deleted tile and
    only a full Chromium restart cleared it."""
    source = KIOSK_JS.read_text()

    assert 'data.type === "refresh"' in source, (
        "kiosk.js ignores the refresh broadcast — ./nora screens will silently "
        "leave the panel stale after every deploy")
    assert "location.reload" in source


def test_the_desk_reuses_the_picker_rather_than_a_second_scroller(client, adult, kiosk_display):
    """The app scroller is Story 45's Picker component in its vertical form —
    "the kiosk's vertical app scroller and the phone's horizontal rail are the
    same control rotated". A second hand-rolled scroller here is how the two
    drift apart."""
    client.force_login(adult)
    body = client.get("/home/displays/kiosk/").content.decode()

    assert 'data-nh-picker data-orientation="vertical"' in body
    assert "nh-picker" in body, "the Picker's own script is not loaded"


def test_every_registered_app_declares_an_icon_this_house_can_draw():
    """nora_icon is a name; nora_home.ui.icons is the only thing that turns it
    into a drawing. A name with no entry renders as nothing at all — which on
    the kiosk's scroller is an unlabelled blank where an app should be."""
    from nora_home.core.registry import registered_apps
    from nora_home.ui.icons import icon, names

    missing = [a.slug for a in registered_apps() if a.nav and not icon(a.icon)]

    assert not missing, (
        f"{missing} declare an icon nora_home.ui.icons cannot draw; "
        f"known names are {names()}")


def test_the_bank_legend_is_derived_not_hardcoded():
    """The mockup draws a fixed "Bank 1 / 1", which is true of a two-app
    prototype and silently becomes wrong the first time an app declares more
    controls than fit. The real panel computes it from what actually
    overflows."""
    source = KIOSK_JS.read_text()

    assert "updateBankLabel" in source
    assert "scrollHeight" in source, "the bank legend is not derived from real overflow"


# ── the control channel (Story 51) ───────────────────────────────────────────

@pytest.mark.django_db
def test_zoom_from_the_panel_writes_the_house_setting():
    """The panel does not carry zoom state — it nudges the stored setting and
    the wall reloads at whatever was saved."""
    from nora_home.ui import zoom as zoom_settings

    zoom_settings.save({"wall": 1.0, "kiosk": 1.0})
    consumer = KioskConsumer()

    stored = consumer._apply_zoom.__wrapped__(consumer, "wall", 0.25)

    assert stored == pytest.approx(1.25)
    assert zoom_settings.stored()["wall"] == pytest.approx(1.25)


@pytest.mark.django_db
@pytest.mark.parametrize("surface,target_attr,ceiling", [
    ("wall", "NORA_HOME_MAIN_DISPLAY_SLUG", 2.0),
    ("kiosk", "NORA_HOME_KIOSK_DISPLAY_SLUG", 1.2),
])
def test_the_panel_cannot_drive_a_screen_past_its_own_ceiling(
        surface, target_attr, ceiling):
    """Holding "+" must stop at the clamp rather than walking a screen to a
    size that breaks it — the kiosk's ceiling is lower than the wall's because
    its layout viewport drops under the 860px breakpoint first."""
    from django.conf import settings as dj_settings

    from nora_home.ui import zoom as zoom_settings

    zoom_settings.save({"wall": 1.0, "kiosk": 1.0})
    consumer = KioskConsumer()
    target = getattr(dj_settings, target_attr)

    stored = None
    for _ in range(40):                     # far past the ceiling on purpose
        stored = consumer._apply_zoom.__wrapped__(consumer, target, 0.25)

    assert stored == pytest.approx(ceiling)


@pytest.mark.django_db
def test_a_nonsense_zoom_delta_leaves_the_screen_alone():
    """The delta arrives as a string off a data attribute; a malformed one
    must not move the wall or raise inside the consumer."""
    from nora_home.ui import zoom as zoom_settings

    zoom_settings.save({"wall": 1.15, "kiosk": 1.0})
    consumer = KioskConsumer()

    stored = consumer._apply_zoom.__wrapped__(consumer, "wall", "sideways")

    assert stored == pytest.approx(1.15)


def test_the_wall_integrates_a_scroll_rate_rather_than_a_position():
    """The wheel is spring-centred, so the message is a rate. A position would
    need the panel to know how long the wall's page is, which it cannot."""
    source = WALL_LIVE_JS.read_text()

    assert "setScrollRate" in source
    assert "data.rate" in source
    assert "scrollBy" in source, "the wall never actually moves its content"


def test_the_wall_stops_scrolling_when_the_wheel_is_released():
    """A rate of 0 must tear the interval down. An always-on screen left
    scrolling forever because nobody sent a stop is the failure this shape
    invites."""
    source = WALL_LIVE_JS.read_text()

    assert "clearInterval" in source, "the scroll interval is never cleared"


def test_the_bend_wheel_sends_zero_on_release():
    source = KIOSK_JS.read_text()

    assert "pointerup" in source and "rate: 0" in source, (
        "releasing the wheel does not stop the wall")
    assert "setPointerCapture" in source, (
        "without pointer capture, releasing off the wheel never delivers the "
        "stop and the wall scrolls forever")
