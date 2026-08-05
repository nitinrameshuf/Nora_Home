"""
The contract every house app must satisfy.

Nothing here is specific to any one app: it walks whatever is installed and
checks the promises the platform makes about house apps on their behalf. A
family member's agent that drops a new app in gets these checks for free, and
finds out at test time rather than when the wall display goes blank.

An app's *own* behaviour is tested in its own suite — see the app's folder under
docs/House_Apps/ and its testing.md. This file is the floor, not the ceiling.
"""

from __future__ import annotations

from importlib import import_module
from importlib.util import find_spec
from pathlib import Path

import pytest
from django.conf import settings

from nora_home.core.cards import Card, load_card
from nora_home.core.registry import RESERVED_SLUGS, house_apps
from nora_home.dashboard.widgets import Widget, load_widget

pytestmark = pytest.mark.django_db

INSTALLED = house_apps()
# Parametrizing by slug keeps the report readable: a failure names the app.
APP_IDS = [meta.slug for meta in INSTALLED]


@pytest.fixture(params=INSTALLED, ids=APP_IDS)
def app(request):
    return request.param


def test_at_least_one_house_app_is_installed():
    """If this fails, every other test in this file passed vacuously."""
    assert INSTALLED, "no house apps are installed; the contract tests proved nothing"


# ── identity ─────────────────────────────────────────────────────────────────

def test_the_app_declares_who_it_is(app):
    assert app.slug, f"{app.module} has no nora_slug"
    assert app.title, f"{app.slug} has no title"
    assert app.description, (
        f"{app.slug} has no nora_description — it appears blank in the Apps "
        "directory and in the MCP tool listing")


def test_the_slug_is_url_safe(app):
    assert app.slug.replace("-", "").replace("_", "").isalnum(), (
        f"{app.slug!r} is not usable as a URL segment")


def test_the_app_does_not_claim_a_platform_prefix(app):
    """House apps mount at the URL root alongside /home, /admin and /api, so a
    collision would shadow part of the platform."""
    first_segment = app.url_prefix.strip("/").split("/")[0]

    assert first_segment not in RESERVED_SLUGS, (
        f"{app.slug} wants /{first_segment}/, which the platform reserves")


def test_the_category_is_a_real_one(app):
    from nora_home.core.registry import Category

    assert app.category in Category.ORDER, (
        f"{app.slug} is in category {app.category!r}, which no nav group renders")


def test_the_minimum_role_is_a_real_one(app):
    assert app.minimum_role in {"member", "adult", "admin"}


# ── the five surfaces ────────────────────────────────────────────────────────

def test_an_app_with_a_page_ships_urls(app):
    if not app.has_page:
        pytest.skip(f"{app.slug} declares no page of its own")

    assert find_spec(f"{app.module}.urls") is not None, (
        f"{app.slug} claims nora_has_page but has no urls.py; the Apps directory "
        "would link to a 404")


def test_the_apps_page_actually_loads(client, admin_member, app):
    if not app.has_page:
        pytest.skip(f"{app.slug} declares no page of its own")
    client.force_login(admin_member)

    assert client.get(app.url).status_code == 200


def test_every_declared_widget_loads(app):
    for dotted in app.widgets:
        widget = load_widget(dotted, app)
        assert widget is not None, f"{app.slug} declares widget {dotted}, which fails to load"
        assert isinstance(widget, Widget)
        assert widget.title, f"{dotted} has no title; it is unpickable in the widget menu"


def test_every_declared_card_loads(app):
    for dotted in app.dashboard_cards:
        card = load_card(dotted, app)
        assert card is not None, f"{app.slug} declares card {dotted}, which fails to load"
        assert isinstance(card, Card)


def test_every_declared_wall_panel_loads_and_is_wall_safe(app):
    """The 24" runs unattended for days. A panel that is not wall-safe should not
    be offered to it."""
    for dotted in app.wall_panels:
        panel = load_card(dotted, app)
        assert panel is not None, f"{app.slug} declares wall panel {dotted}, which fails to load"
        assert panel.wall_safe, f"{dotted} is on the wall but is not wall_safe"


def test_kiosk_controls_are_well_formed(app):
    """The 10.1" kiosk renders these as buttons. A missing path is a button that
    does nothing; a Django URL name instead of a path is the same."""
    for control in app.kiosk_controls:
        assert isinstance(control, dict), f"{app.slug}: kiosk control {control!r} is not a dict"
        assert control.get("title"), f"{app.slug} has a kiosk control with no title"
        path = control.get("path", "")
        assert path.startswith("/"), (
            f"{app.slug}: kiosk control {control['title']!r} has path {path!r}; "
            "kiosk controls take plain paths, not URL names")


def test_kiosk_control_paths_resolve(app):
    from django.urls import Resolver404, resolve

    for control in app.kiosk_controls:
        try:
            resolve(control["path"])
        except Resolver404:
            pytest.fail(f"{app.slug}: kiosk control {control['title']!r} points at "
                        f"{control['path']}, which does not resolve")


# ── the platform's own rules ─────────────────────────────────────────────────

# Existing violations of the "never import another app's models" rule, recorded
# rather than hidden. New apps get the rule enforced strictly; this list is the
# debt that predates the test, and it should only ever shrink.
#
# example_habit reads nora_home.tracker.models directly in five files to build
# streaks and completion history. It is the *reference* app — the one
# DEVELOPMENT.md tells every family member to copy — so it currently teaches the
# pattern the platform forbids. Clearing it needs query functions on
# nora_home.tracker.api that do not exist yet (streaks for a source_ref,
# completion history, the open occurrence for a record). See
# docs/Main_App/testing.md § Known gaps.
KNOWN_MODEL_IMPORT_DEBT = {
    "habits": {"nora_home.tracker.models"},
}


def test_the_app_does_not_import_another_apps_models(app):
    """"Never import another app's models" (CLAUDE.md §6) — it is what lets an
    app be uninstalled without breaking the house. Use the published APIs."""
    package_dir = Path(import_module(app.module).__file__).parent
    own_prefix = f"{app.module}."
    allowed = KNOWN_MODEL_IMPORT_DEBT.get(app.slug, set())
    offenders = []

    for source in package_dir.rglob("*.py"):
        if "migrations" in source.parts:
            continue
        text = source.read_text(encoding="utf-8", errors="ignore")
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith(("from ", "import ")):
                continue
            if ".models import" not in line and not line.endswith(".models"):
                continue
            # Its own models are fine. So are the platform's base models (the
            # documented inheritance path) and HouseMember (AUTH_USER_MODEL —
            # every app references people, and Django offers no way around it).
            if own_prefix in line or "nora_home.core.models" in line:
                continue
            if "nora_home.accounts.models" in line:
                continue
            if any(module in line for module in allowed):
                continue
            offenders.append(f"{source.name}: {line}")

    assert not offenders, (
        f"{app.slug} imports another app's models directly:\n  "
        + "\n  ".join(offenders)
        + "\nUse nora_home.<app>.api or a signal from nora_home.core.signals instead.")


def test_recorded_debt_is_still_real():
    """Stops the exemption list above from rotting. Once an app is cleaned up,
    its entry has to go — otherwise the list quietly re-permits the rule it was
    meant to be a temporary exception to."""
    for slug, modules in KNOWN_MODEL_IMPORT_DEBT.items():
        meta = next((m for m in INSTALLED if m.slug == slug), None)
        if meta is None:
            pytest.fail(f"{slug} is in the debt list but is not installed; remove it")

        package_dir = Path(import_module(meta.module).__file__).parent
        sources = "\n".join(
            source.read_text(encoding="utf-8", errors="ignore")
            for source in package_dir.rglob("*.py")
            if "migrations" not in source.parts
        )
        for module in modules:
            assert module in sources, (
                f"{slug} no longer imports {module} — remove it from "
                "KNOWN_MODEL_IMPORT_DEBT so the rule is enforced again")


def test_the_app_does_not_read_the_environment_directly(app):
    """"No app reads os.environ directly" (CLAUDE.md §6) — settings go in
    config/settings/base.py with a default so the house boots without them."""
    package_dir = Path(import_module(app.module).__file__).parent
    offenders = [
        source.name for source in package_dir.rglob("*.py")
        if "migrations" not in source.parts
        and "os.environ" in source.read_text(encoding="utf-8", errors="ignore")
    ]

    assert not offenders, (
        f"{app.slug} reads os.environ in {offenders}; add the setting to "
        "config/settings/base.py and read it via django.conf.settings")


def test_every_model_inherits_a_platform_base(app):
    """"Every model inherits from a base in nora_home/core/models.py" — at
    minimum TimeStampedModel, so "who touched this and when" stays answerable."""
    from django.apps import apps as django_apps
    from nora_home.core.models import TimeStampedModel

    config = django_apps.get_app_config(app.module.rsplit(".", 1)[-1])

    for model in config.get_models():
        assert issubclass(model, TimeStampedModel), (
            f"{app.slug}.{model.__name__} does not inherit TimeStampedModel")


def test_the_app_has_migrations(app):
    """The entrypoint runs `migrate` on every start, so an app with no committed
    migration deploys as an app with no tables."""
    package_dir = Path(import_module(app.module).__file__).parent
    migrations = package_dir / "migrations"

    if not any(m.name.startswith("0001") for m in migrations.glob("*.py")):
        pytest.fail(f"{app.slug} has no initial migration; run makemigrations "
                    "and commit the result")


# ── documentation duty ───────────────────────────────────────────────────────

def test_the_app_has_a_docs_folder(app):
    """"Every house app is required to have a folder under docs/House_Apps/
    with a README.md" (CLAUDE.md §0). install_app warns; this fails."""
    name = app.module.rsplit(".", 1)[-1]
    readme = Path(settings.BASE_DIR) / "docs" / "House_Apps" / name / "README.md"

    assert readme.exists(), f"missing docs/House_Apps/{name}/README.md"


def test_the_app_has_approved_requirements(app):
    """Gate 1 of the workflow in DEVELOPMENT.md: what the app does, written in
    plain language and approved by the user before any code was written. An app
    without one is an app whose functionality was never agreed."""
    name = app.module.rsplit(".", 1)[-1]
    requirements = Path(settings.BASE_DIR) / "docs" / "House_Apps" / name / "requirements.md"

    assert requirements.exists(), (
        f"missing docs/House_Apps/{name}/requirements.md — see DEVELOPMENT.md "
        "section 'The workflow'")


def test_the_app_documents_how_to_test_it(app):
    """Each house app carries its own testing.md, the same way the base app
    does — so the next person knows what "verified" means for this app."""
    name = app.module.rsplit(".", 1)[-1]
    testing = Path(settings.BASE_DIR) / "docs" / "House_Apps" / name / "testing.md"

    assert testing.exists(), f"missing docs/House_Apps/{name}/testing.md"
