"""The platform's promise to an app author, made executable.

`docs/Main_App/DEVELOPMENT.md` tells a family member's agent that declaring a
`NoraAppConfig` is enough: the app then appears in the sidebar, on the phone,
on the kiosk, in the widget picker, and at its own URL, with no platform change.
`tests/test_house_apps.py` checks that whatever *is* installed obeys the rules.
Neither checks that the promise itself still works — that a newly declared app
actually reaches every surface.

That gap is not hypothetical. `register_trackable()` was documented in five
files as the call an app makes to hand the house a recurring job; Story 40
deleted the app that published it, and the documentation went on promising it
for weeks because nothing executed it.

So this file installs `tests/contract_app` — a house app declared exactly as
the documentation describes — and asserts each surface picks it up. A surface
that stops deriving from the registry fails here rather than being noticed on
a screen months later.

Why override_settings rather than adding it to config.settings.test: the app is
a *fixture*, not a shipped reference app. The old reference app was removed
deliberately (see config/settings/test.py), and forcing one back into every
test run would undo that. `override_settings(INSTALLED_APPS=...)` repopulates
Django's app registry for the duration of the test, which is all this needs.

The fixture has no models on purpose. Django will not migrate an app added
after the test database was built, and nothing the contract covers needs tables.
"""

from __future__ import annotations

import pytest
from django.apps import apps as django_apps
from django.conf import settings
from django.test import override_settings
from django.urls import Resolver404, resolve, reverse

from nora_home.core.registry import house_apps, navigation, registered_apps
from nora_home.dashboard.widgets import Widget, load_widget

CONTRACT_APP = "tests.contract_app"
SLUG = "contractapp"


@pytest.fixture
def installed():
    """The app, installed, with URLs rebuilt so its pages actually resolve.

    house_app_urlpatterns() is evaluated when config.urls is imported, so a
    registry change alone does not create routes — the URL conf has to be
    cleared and rebuilt too. Getting this wrong makes every path assertion
    fail for a reason that has nothing to do with the app.
    """
    from django.urls import clear_url_caches
    import importlib
    import config.urls

    with override_settings(INSTALLED_APPS=[*settings.INSTALLED_APPS, CONTRACT_APP]):
        importlib.reload(config.urls)
        clear_url_caches()
        yield next(a for a in registered_apps() if a.slug == SLUG)

    importlib.reload(config.urls)
    clear_url_caches()


# ── it is discovered at all ──────────────────────────────────────────────────

def test_declaring_an_app_is_enough_to_register_it(installed):
    """No platform file is edited to add an app. This is the whole premise."""
    assert installed.slug == SLUG
    assert installed.title == "Contract App"
    assert installed.description, "an app with no description is blank in every picker"


def test_it_counts_as_a_house_app_not_a_platform_one(installed):
    """Level 3 is the default, and house_apps() is what the Apps directory lists."""
    assert installed.level == 3
    assert installed.slug in {a.slug for a in house_apps()}


# ── every surface derives from that one declaration ──────────────────────────

def test_it_reaches_the_navigation(installed):
    """The sidebar, the phone's rail and the kiosk's scroller all read
    navigation(); if it is absent here it is absent from all three."""
    listed = {a.slug for group in navigation("admin") for a in group["apps"]}

    assert installed.slug in listed


def test_it_reaches_the_rendered_sidebar(client, admin_member, installed):
    """The data check above is not the same claim as this one — Story 54 found
    the gap the hard way: desktop_shell.html hand-codes Home's own group and
    only *filters* the Apps loop by slug, so a registry entry can be entirely
    correct in navigation()'s return value while a template change still
    leaves it unrendered (or renders it in the wrong place). "Reaches every
    surface" has to mean the HTML a browser actually gets, not just the data
    a template would have read from if it asked."""
    client.force_login(admin_member)

    body = client.get(reverse("core:dashboard")).content.decode()

    assert installed.title in body, (
        f"{installed.slug} is in navigation() but never rendered into the sidebar")


def test_its_page_is_mounted_and_loads(client, admin_member, installed):
    client.force_login(admin_member)

    assert client.get(installed.url).status_code == 200


def test_every_section_resolves_and_loads(client, admin_member, installed):
    """Sections are the sidebar's sub-nav, the phone's section rail and — from
    Phase 8 — the kiosk's key bank. A section that 404s is a dead end on three
    surfaces at once."""
    client.force_login(admin_member)
    assert installed.sections, "the fixture declares sections; the contract covers them"

    for section in installed.sections:
        assert client.get(section["path"]).status_code == 200, section["title"]


def test_every_kiosk_control_resolves(installed):
    """The kiosk sends the wall to a path. One that does not resolve is a key
    that does nothing, with no error anywhere."""
    assert installed.kiosk_controls

    for control in installed.kiosk_controls:
        try:
            resolve(control["path"])
        except Resolver404:
            pytest.fail(f"kiosk control {control['title']!r} -> {control['path']} does not resolve")


def test_every_declared_widget_loads_and_renders(installed):
    """A widget that fails to load is silently missing from the picker."""
    assert installed.widgets

    for dotted in installed.widgets:
        widget = load_widget(dotted, installed)
        assert widget is not None, f"{dotted} failed to load"
        assert isinstance(widget, Widget)
        assert widget.title, f"{dotted} has no title and is unpickable"


# ── the promise holds without touching the platform ──────────────────────────

def test_the_app_needed_no_platform_edits(installed):
    """The strongest form of the claim: the app declares itself, and nothing in
    nora_home/ or config/ names it."""
    import subprocess

    hits = subprocess.run(
        ["grep", "-rl", SLUG, "nora_home", "config", "templates"],
        capture_output=True, text=True, cwd=settings.BASE_DIR,
    ).stdout.split()

    assert not hits, f"the platform names this app in {hits} — it should not have to"


def test_uninstalling_it_leaves_no_trace(installed):
    """An app is uninstallable; the registry must not remember it afterwards."""
    assert installed.slug in {a.slug for a in registered_apps()}


def test_registry_is_clean_once_the_app_is_gone():
    """Runs outside the fixture: by now the app is uninstalled again."""
    assert SLUG not in {a.slug for a in registered_apps()}
    assert not django_apps.is_installed(CONTRACT_APP)


# ── nora_actions: declare once, derive everywhere (Story 57) ─────────────────
#
# A verb an app declares is supposed to reach two surfaces automatically: a
# real button on desktop/phone (data-action="<verb>"), and — only when
# kiosk=True — a key on the kiosk's own "Do" row (data-kiosk-action="appaction"
# data-verb="<verb>"). wall-live.js's own handler for "appaction" is already
# covered by test_displays.py's "every relayed kiosk action has a handler"
# check. What's missing without these tests: an app could declare a verb with
# no real button behind it anywhere, and nothing would fail — "a dead button
# with no error anywhere," the exact shape of bug nora_actions exists to rule
# out.

def test_every_declared_action_has_the_right_shape():
    """Every nora_actions entry across every registered app, not just Home
    and Todo — this is the structural contract the other two tests below
    assume holds before they go looking for a real button."""
    for meta in registered_apps():
        for action in meta.actions:
            assert set(action) >= {"verb", "title", "kiosk"}, (
                f"{meta.slug}'s action {action!r} is missing a required key")
            assert isinstance(action["kiosk"], bool), (
                f"{meta.slug}'s action {action['verb']!r} kiosk flag is not a bool")


@pytest.mark.django_db
def test_every_desktop_action_has_a_real_button(client, admin_member):
    """Home's dashboard and Todo's board are where CoreConfig/TodoConfig's own
    nora_actions verbs live today — checked against the actually-rendered
    HTML, not the registry's own claim about itself (test_it_reaches_the_
    rendered_sidebar, Story 55, is the same discipline applied here)."""
    client.force_login(admin_member)

    core_actions = django_apps.get_app_config("core").nora_actions
    home_body = client.get(reverse("core:dashboard")).content.decode()
    for action in core_actions:
        assert f'data-action="{action["verb"]}"' in home_body, (
            f"Home declares {action['verb']!r} but /home/ has no button for it")

    todo_actions = django_apps.get_app_config("todo").nora_actions
    board_body = client.get(reverse("todo:board")).content.decode()
    for action in todo_actions:
        assert f'data-action="{action["verb"]}"' in board_body, (
            f"Todo declares {action['verb']!r} but /todo/ has no button for it")


@pytest.mark.django_db
def test_every_kiosk_eligible_action_has_a_key_on_the_desk(client, admin_member,
                                                            kiosk_display):
    """Only kiosk:True verbs should reach the desk at all — a kiosk:False verb
    (add-widget, new-task) needs a choice or typing and correctly stays off
    it, so this also guards against one leaking onto a physical key."""
    client.force_login(admin_member)

    body = client.get(reverse("displays:kiosk")).content.decode()

    for meta in registered_apps():
        if meta.slug != "todo":
            continue
        for action in meta.actions:
            marker = f'data-verb="{action["verb"]}"'
            if action["kiosk"]:
                assert marker in body, (
                    f"{action['verb']!r} is kiosk:True but has no key on the desk")
            else:
                assert marker not in body, (
                    f"{action['verb']!r} is kiosk:False but rendered a key anyway")

    core_actions = django_apps.get_app_config("core").nora_actions
    for action in core_actions:
        marker = f'data-verb="{action["verb"]}"'
        if action["kiosk"]:
            assert marker in body, (
                f"Home's {action['verb']!r} is kiosk:True but has no key on the desk")
        else:
            assert marker not in body, (
                f"Home's {action['verb']!r} is kiosk:False but rendered a key anyway")
