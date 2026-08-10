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


def test_a_link_clicked_inside_the_walls_iframe_is_still_the_wall(rf):
    """The regression test for the bug that made the 24" quietly stop being
    the 24".

    Only the *first* hop carries the shell page as its referer. Navigate by
    clicking the sidebar on the wall itself and the referer is the previous
    app page, so the shell-prefix check above misses and the surface fell all
    the way back to User-Agent — laptop type scale, wall zoom dropped, no
    error anywhere. Same-origin plus Sec-Fetch-Dest is what covers this hop.
    """
    surface = _surface(rf, "/todo/calendar/", MAC, HTTP_SEC_FETCH_DEST="iframe",
                       HTTP_REFERER="http://testserver/todo/")

    assert surface["surface"] == "wall"


def test_an_iframe_from_another_origin_is_not_the_wall(rf):
    """Sec-Fetch-Dest alone is not enough — anything could iframe the app.
    Same-origin is the line: a page elsewhere embedding the house either sends
    no Referer or sends its own, and fails this either way."""
    surface = _surface(rf, "/home/", MAC, HTTP_SEC_FETCH_DEST="iframe",
                       HTTP_REFERER="https://somewhere-else.example/page/")

    assert surface["surface"] == "desktop"


def test_an_ordinary_click_on_a_laptop_is_not_the_wall(rf):
    """The guard on the rule above. Every normal navigation also carries a
    same-origin referer — it is Sec-Fetch-Dest that says "this document is in
    a frame", and without it nothing here may promote a page to the wall."""
    surface = _surface(rf, "/todo/", MAC, HTTP_SEC_FETCH_DEST="document",
                       HTTP_REFERER="http://testserver/home/")

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
# Story 44 replaced root-font-size scaling with CSS `zoom` (nora_home/ui/
# zoom.py) specifically because zoom scales *every* length unit — px included
# — while root-font-size only ever reached rem, which is what let a stray px
# value (Gridstack's cellHeight: 80, then --nav-width: 244px cutting
# "Measurements" mid-word) clip on the real 24" while every rem value around
# it grew correctly. Under zoom that whole class of bug cannot recur — px and
# rem now scale identically — so the old "must be rem" tests these two names
# used to enforce (test_layout_tokens_are_rem_so_the_wall_scale_reaches_them,
# test_the_card_grid_minimum_is_rem_not_px) are retired along with the
# stylesheet they read, not carried forward: their premise is the thing that
# changed, not just their target file.
#
# What's still real and still worth a test: no root-font-size scaling comes
# back, and the wall's cursor stays gated on the idle flag — both now read
# from the new system's own files (Story 45, Phase B).

def _new_css() -> str:
    from pathlib import Path

    from django.conf import settings

    base = Path(settings.BASE_DIR) / "assets" / "css"
    return (base / "shell.css").read_text(encoding="utf-8") + (
        base / "components.css").read_text(encoding="utf-8")


def test_the_type_scale_is_not_in_the_stylesheet():
    """Scaling the root font-size was tried twice (160%, then 135%) and was
    wrong both times: it grows every rem while borders, shadows and radii stay
    1-device-pixel hairlines, so the proportions come apart and it reads as
    zoomed even when the text size is right. Putting it back is the tempting
    wrong move, so this asserts it has not come back."""
    import re

    assert not re.search(r'html\[data-surface="wall"\]\s*\{\s*font-size', _new_css()), (
        "the wall's type scale is back in CSS — see the comment on that rule")


def test_the_wall_only_hides_the_cursor_while_it_is_idle():
    """The wall hid its pointer outright until 2026-08-07, left over from when
    it was a passive ambient view. It is the real app now and gets clicked
    directly, so every `cursor: none` has to stay behind the idle flag that
    nh-app.js clears on the first mouse move — otherwise the sidebar has to be
    aimed at blind. Regressed once already in Story 45, Phase B: deleting
    nora-home.css deleted this rule with it, since nothing had re-added it to
    shell.css yet — found by this test, not by looking at the wall."""
    import re

    for selector, body in re.findall(r"([^{}]*)\{([^{}]*)\}", _new_css()):
        if re.search(r"cursor:\s*none", body):
            assert 'data-cursor="idle"' in selector, (
                f"`cursor: none` is not gated on the idle flag: {selector.strip()!r}")


def test_the_screens_launch_unscaled_so_the_setting_is_the_only_scale():
    """The device scale factor and the stored zoom would multiply together if
    both were set, and the launch flag is the one nobody can see from the app."""
    import re
    from pathlib import Path

    from django.conf import settings

    provision = (Path(settings.BASE_DIR) / "scripts" / "lib" / "provision-pi.sh"
                 ).read_text(encoding="utf-8")

    for screen in ("wall", "kiosk"):
        call = re.search(rf'launch_script\s+"{screen}".*', provision)
        assert call, f"the {screen} is no longer launched from provision-pi.sh"
        scale = call.group(0).split()[-1]
        assert scale in ("1", '"1024,600"'), (
            f"the {screen} launches at scale {scale} — that would multiply with "
            f"the zoom stored in Settings")


# ── the Story 44 token layer ───────────────────────────────────────────────
#
# tokens.css is grounded in docs/Main_App/ui-overhaul-mockup.html's own token
# layer — these tests check the two have not drifted apart, not that the
# numbers are individually "right". If the mockup changes, this file and these
# tests both do, in the same commit.

def _tokens() -> str:
    from pathlib import Path

    from django.conf import settings

    return (Path(settings.BASE_DIR) / "assets" / "css" / "tokens.css").read_text(
        encoding="utf-8")


def _mockup() -> str:
    from pathlib import Path

    from django.conf import settings

    return (Path(settings.BASE_DIR) / "docs" / "Main_App" / "ui-overhaul-mockup.html"
            ).read_text(encoding="utf-8")


def _ramp_values(css: str) -> list[tuple[str, str]]:
    """--token: value pairs for the ramp tokens, in file order and whitespace-
    insensitive. The base block and each surface override all redefine some of
    these names, so order (not a dict, which would keep only the last
    definition of each) is what makes this catch a value copied into the wrong
    surface's block."""
    import re

    return re.findall(
        r"(--s[0-4]|--lab|--gap|--pad|--rad|--tap|--row):\s*([\w.]+px)", css)


def test_the_ramp_matches_the_approved_mockup():
    """The mockup is the reference (CLAUDE.md §4): a ramp value copied wrong
    here is a UI decision nobody actually saw and approved."""
    mockup_values = _ramp_values(_mockup())
    assert mockup_values, "no ramp tokens found in the mockup — did it move?"
    assert _ramp_values(_tokens()) == mockup_values, (
        "tokens.css's ramp does not match the mockup's, token-for-token in order")


@pytest.mark.parametrize("surface", ["phone", "kiosk", "wall"])
def test_every_non_base_surface_has_its_own_ramp(surface):
    assert f'html[data-surface="{surface}"]' in _tokens()


def test_the_font_is_self_hosted_not_a_cdn():
    """The Pi has to render with the internet down — same reason ECharts and
    Gridstack are vendored rather than pulled live. A Google Fonts @import
    would work in every browser tab used to build this and fail silently the
    first time the house's internet drops."""
    tokens = _tokens()
    assert "@import url(https://fonts" not in tokens
    assert "fonts.googleapis.com" not in tokens
    assert "@fontsource-variable/inter" in tokens
    assert "@fontsource-variable/jetbrains-mono" in tokens


def test_the_colour_tokens_are_not_routed_through_theme():
    """Tailwind v4's @theme always namespaces what it emits — a colour
    declared as `--arc-500` inside @theme actually compiles to
    `--color-arc-500`, and everything that consumes it (components.css, the
    styleguide, the mockup these are copied from) reads plain var(--arc-500).
    The mismatch does not error: the property is simply unset, so `color:
    var(--arc-500)` silently paints nothing and every glow/border stayed
    visible while the text and fills it was meant to colour did not — found
    only by looking at a screenshot. @theme is for --font-sans/--font-mono
    only, which need no prefix (font is already their namespace) and which
    Tailwind's own base layer forces into the output regardless."""
    import re

    tokens = _tokens()
    theme_block = re.search(r"@theme\s*\{([^}]*)\}", tokens, re.S)
    assert theme_block, "no @theme block — did the font declarations move?"
    theme_keys = re.findall(r"--([\w-]+):", theme_block.group(1))
    assert set(theme_keys) == {"font-sans", "font-mono"}, (
        f"@theme declares {theme_keys} — anything beyond the two font names "
        "compiles to --color-<name> and stops matching var(--<name>) "
        "everywhere else")

    for name in ("arc-500", "ok", "warn", "crit", "txt", "dim", "faint"):
        assert re.search(rf"[^-]--{name}:", tokens), (
            f"--{name} is not a plain custom property in tokens.css")


def test_the_arc_reactor_palette_is_dark_only():
    """Story 44's notes: the light theme is deleted rather than rebuilt. A
    `--color-arc-*` variable reappearing under a `[data-theme="light"]`
    selector would mean it crept back in for this layer specifically."""
    assert '[data-theme="light"]' not in _tokens()


@pytest.mark.parametrize("template", [
    "templates/base.html",
    "templates/displays/kiosk.html",
    "templates/displays/wall_live.html",
    "templates/accounts/switch.html",
])
def test_every_page_shell_loads_tokens_before_the_rest(template):
    """Four separate page shells exist (base, kiosk, wall, the switcher) because
    the kiosk and wall deliberately do not extend base.html. Missing one of them
    here is exactly the kind of thing that reaches three surfaces and not the
    fourth without anyone noticing — CLAUDE.md §4 on the sidebar/nav bug."""
    import re
    from pathlib import Path

    from django.conf import settings

    text = (Path(settings.BASE_DIR) / template).read_text(encoding="utf-8")
    links = re.findall(r"vite_asset_url '(assets/css/[\w-]+\.css)'", text)

    assert links, f"{template} loads no stylesheets at all"
    assert links[0] == "assets/css/tokens.css", (
        f"{template} loads {links[0]!r} first — tokens.css must come first so "
        "its custom properties exist before anything might read them")


# ── screen zoom, set from Settings ───────────────────────────────────────────

@pytest.mark.django_db
class TestScreenZoom:
    """nora_home/ui/zoom.py — the one thing a browser cannot work out for
    itself, so the person in front of the screen sets it."""

    def test_the_defaults_are_the_measured_ones(self):
        from nora_home.ui import zoom

        assert zoom.stored() == {"wall": 1.25, "kiosk": 1.0}

    def test_saving_round_trips(self):
        from nora_home.ui import zoom

        zoom.save({"wall": 1.4, "kiosk": 1.1})

        assert zoom.stored() == {"wall": 1.4, "kiosk": 1.1}

    def test_values_are_clamped_per_screen(self):
        """The kiosk's ceiling is lower than the wall's: at 1024 physical, a big
        zoom puts the layout viewport under the 860px breakpoint while media
        queries still report 1024, so the narrow rules never fire."""
        from nora_home.ui import zoom

        saved = zoom.save({"wall": 99, "kiosk": 99})

        assert saved["wall"] == zoom.MAX_ZOOM["wall"]
        assert saved["kiosk"] == zoom.MAX_ZOOM["kiosk"]
        assert zoom.clamp("wall", 0.01) == zoom.MIN_ZOOM

    def test_nonsense_falls_back_rather_than_raising(self):
        """This is read on the way to rendering the always-on wall. A bad stored
        value must not be able to take that screen down."""
        from nora_home.ui import zoom

        assert zoom.clamp("wall", "banana") == zoom.DEFAULTS["wall"]
        assert zoom.clamp("wall", None) == zoom.DEFAULTS["wall"]

    def test_a_corrupted_setting_still_yields_usable_numbers(self):
        from nora_home.core.settings_store import set_setting
        from nora_home.ui import zoom

        set_setting(zoom.SETTING_KEY, "not a dict at all", app_slug="displays")

        assert zoom.stored() == {"wall": 1.25, "kiosk": 1.0}

    @pytest.mark.parametrize("surface", ["desktop", "phone", "tablet"])
    def test_handheld_surfaces_get_no_zoom_at_all(self, surface):
        """"for displays like laptop or phone, it already looks fine" — those
        are held at arm's length, which is what every browser default assumes.
        None rather than 1.0, so the template emits no style attribute."""
        from nora_home.ui import zoom

        assert zoom.for_surface(surface) is None

    def test_a_screen_set_to_1_also_emits_nothing(self):
        from nora_home.ui import zoom

        zoom.save({"wall": 1.0, "kiosk": 1.0})

        assert zoom.for_surface("wall") is None

    def test_the_wall_carries_its_zoom_into_the_markup(self, client, admin_member):
        from django.urls import reverse

        from nora_home.ui import zoom

        zoom.save({"wall": 1.4, "kiosk": 1.0})
        client.force_login(admin_member)

        body = client.get(reverse("core:dashboard"),
                          HTTP_SEC_FETCH_DEST="iframe",
                          HTTP_REFERER="http://testserver/home/displays/wall/").content.decode()

        assert 'style="zoom: 1.4"' in body

    def test_a_laptop_gets_no_zoom_attribute(self, client, admin_member):
        from django.urls import reverse

        client.force_login(admin_member)

        body = client.get(reverse("core:dashboard")).content.decode()

        assert "zoom:" not in body

    def test_the_settings_page_saves_it(self, client, admin_member):
        from django.urls import reverse

        from nora_home.ui import zoom

        client.force_login(admin_member)

        client.post(reverse("core:settings"),
                    {"form": "zoom", "zoom_wall": "1.35", "zoom_kiosk": "1.05"})

        assert zoom.stored() == {"wall": 1.35, "kiosk": 1.05}

    def test_saving_a_zoom_does_not_disturb_the_power_schedule(self, client, admin_member):
        """Two independent forms on one page. Posting either must not silently
        rewrite the other's setting with whatever the browser did not send."""
        from django.urls import reverse

        from nora_home.core.settings_store import get_setting

        client.force_login(admin_member)
        client.post(reverse("core:settings"), {
            "wall_schedule_enabled": "on", "wall_schedule_start": "7",
            "wall_schedule_end": "23"})

        client.post(reverse("core:settings"),
                    {"form": "zoom", "zoom_wall": "1.3", "zoom_kiosk": "1"})

        schedule = get_setting("displays.wall_power_schedule")
        assert schedule["start_hour"] == 7 and schedule["end_hour"] == 23

    def test_changing_it_is_audited_with_the_new_values(self, client, admin_member):
        from django.urls import reverse

        from nora_home.core.models import AuditEvent

        client.force_login(admin_member)
        client.post(reverse("core:settings"),
                    {"form": "zoom", "zoom_wall": "1.3", "zoom_kiosk": "1"})

        event = AuditEvent.objects.filter(action="zoom.changed").first()
        assert event is not None
        assert event.detail["wall_zoom"] == 1.3


# ── Story 45, Phase B: the shell rewrite, and every page converted ────────
#
# Phase B started with a bridge — pages not yet rewired onto components.css
# added nora-home.css back in via their own {% block head %}, since base.html
# stopped loading it centrally — and finished with every real page converted
# and all four old stylesheets (nora-home.css, todo.css, dashboard.css,
# displays.css) deleted. The bridge tests below reflect the end state, not
# the transitional one; see docs/Main_App/progress.md's dated entry for the
# transitional bridge mechanism itself, which no longer exists in the code.

def _shell() -> str:
    from pathlib import Path

    from django.conf import settings

    return (Path(settings.BASE_DIR) / "assets" / "css" / "shell.css").read_text(
        encoding="utf-8")


def test_shell_css_is_not_layered():
    """A cascade layer always loses to unlayered CSS regardless of
    specificity. shell.css was `@layer comp` once, and nora-home.css's bare,
    unlayered `a { color: var(--accent) }` beat `.nav { color: var(--dim) }`
    every time despite `.nav` being the more specific selector — every nav
    label rendered in the old orange accent instead of the rail's own ink
    colour. The shell has to win unconditionally, on every page, bridged or
    not, so it competes with nora-home.css on the same (unlayered) terms."""
    import re

    without_comments = re.sub(r"/\*.*?\*/", "", _shell(), flags=re.S)
    assert "@layer" not in without_comments, (
        "shell.css is layered again — it will lose to any bridged page's "
        "unlayered nora-home.css regardless of selector specificity")


@pytest.mark.django_db
def test_the_rail_never_uses_the_old_sidebar_markup(client, admin_member):
    """base.html's nav was rewritten from .sidebar/.nav-link/.nav-group onto
    .rail/.nav/.grp-lab (Story 45, Phase B) — these two systems must never
    both be present, or the page is carrying dead structure from the rewrite
    rather than having actually completed it."""
    from django.urls import reverse

    client.force_login(admin_member)
    body = client.get(reverse("core:dashboard")).content.decode()

    assert 'class="rail"' in body
    assert 'class="sidebar"' not in body
    assert "nav-link" not in body
    assert "profile-trigger" not in body
    assert "data-theme-toggle" not in body


@pytest.mark.django_db
def test_no_page_bridges_a_stylesheet_that_no_longer_exists(client, admin_member):
    """The bridge (a page adding nora-home.css/todo.css/dashboard.css/
    displays.css back in via its own {% block head %}, since base.html
    stopped loading them centrally) was how every page kept rendering while
    only some had been rewired onto components.css. Once every real page was
    converted, all four old files were deleted — a leftover bridge link would
    now 404 the whole page (DjangoViteAssetNotFoundError) rather than degrade
    gracefully, since django-vite raises when a name isn't in the manifest."""
    from django.urls import reverse

    client.force_login(admin_member)

    for name in ("core:dashboard", "core:system_status",
                 "core:settings", "notifications:inbox",
                 "todo:board", "todo:reporting"):
        body = client.get(reverse(name)).content.decode()
        for old in ("nora-home.css", "todo.css", "dashboard.css", "displays.css"):
            assert old not in body, f"{name} still references deleted {old}"
