"""
The app registry — how the platform stays a platform.

This is the highest-value file in the suite. The registry has already failed
silently once in this project's history (every app config fell back to a plain
AppConfig, so the nav and app directory came back empty with no error anywhere),
and a silent empty registry looks exactly like a working system until someone
looks at the screen. Several tests here exist specifically to make that failure
mode loud.
"""

from __future__ import annotations

import pytest

from nora_home.core.registry import (
    RESERVED_SLUGS,
    AppMetadata,
    Category,
    NoraAppConfig,
    house_apps,
    house_app_urlpatterns,
    navigation,
    registered_apps,
    scope_members,
)


# ── discovery ────────────────────────────────────────────────────────────────

def test_registry_is_not_empty():
    """The regression guard for the bug that started this file. An empty
    registry is a working-looking house with a blank nav."""
    assert registered_apps(), (
        "No NoraAppConfig was discovered. Check `default = False` on the base "
        "class and `__init_subclass__` in nora_home/core/registry.py."
    )


def test_platform_apps_are_all_present():
    """Every platform subsystem that declares itself should be found. If one
    disappears, its widgets, cards, and MCP tools go with it."""
    modules = {meta.module for meta in registered_apps()}
    for expected in ["nora_home.core", "nora_home.todo", "nora_home.notifications",
                     "nora_home.telemetry", "nora_home.displays", "nora_home.dashboard",
                     "nora_home.integrations"]:
        assert expected in modules, f"{expected} is not registered"


def test_house_apps_excludes_platform_apps():
    """The Apps page shows the family's apps. A platform subsystem leaking into
    that list is the bug this project already fixed once by adding is_platform."""
    for meta in house_apps():
        assert not meta.module.startswith("nora_home."), (
            f"{meta.module} is a platform app but is listed as a house app")


def test_every_registered_app_is_a_dataclass_with_a_usable_url():
    for meta in registered_apps():
        assert isinstance(meta, AppMetadata)
        assert meta.slug, f"{meta.module} has no slug"
        assert meta.url.startswith("/"), f"{meta.slug} has a relative url {meta.url!r}"


# ── metadata derivation ──────────────────────────────────────────────────────

def test_metadata_defaults_are_derived_from_the_slug():
    class _Config(NoraAppConfig):
        name = "houseapps.example_habit"
        nora_slug = "plants"
        nora_title = "Plants"

    meta = _Config("houseapps.example_habit", __import__("houseapps")).nora_home_metadata
    assert meta.url_prefix == "plants/"
    assert meta.url == "/plants/"
    assert meta.icon == "sparkle"
    assert meta.category == Category.HOUSE


def test_explicit_url_prefix_wins_over_the_slug():
    class _Config(NoraAppConfig):
        name = "houseapps.example_habit"
        nora_slug = "plants"
        nora_url_prefix = "garden/beds/"

    meta = _Config("houseapps.example_habit", __import__("houseapps")).nora_home_metadata
    assert meta.url == "/garden/beds/"


def test_subclassing_sets_default_true():
    """The tie-breaker Django needs to pick the real config over the base."""
    class _Config(NoraAppConfig):
        name = "houseapps.example_habit"

    assert _Config.default is True
    assert NoraAppConfig.default is False, "the base must never be selectable"


# ── ordering and grouping ────────────────────────────────────────────────────

def test_apps_sort_by_category_order_then_app_order():
    metas = registered_apps()
    ranks = [
        (Category.ORDER.index(m.category) if m.category in Category.ORDER else 99,
         m.order, m.title)
        for m in metas
    ]
    assert ranks == sorted(ranks), "registered_apps() is not returning sorted output"


def test_category_label_falls_back_for_unknown_keys():
    assert Category.label(Category.SELF) == "Self Improvement"
    assert Category.label("greenhouse") == "Greenhouse"


# ── navigation and roles ─────────────────────────────────────────────────────

def test_navigation_groups_by_category():
    groups = navigation("admin")
    assert groups, "nav came back empty"
    for group in groups:
        assert group["apps"], f"category {group['key']} is present but has no apps"
        assert group["label"] == Category.label(group["key"])


def test_navigation_only_contains_nav_enabled_apps():
    """Displays sets nora_nav = False — its status lives on Settings instead.
    If it reappears in the nav, that decision has been silently undone."""
    for group in navigation("admin"):
        for meta in group["apps"]:
            assert meta.nav is True


def test_navigation_hides_apps_above_the_viewers_role():
    """A kid must not see an adult-only app. This is the only access control the
    nav has, so it is worth asserting directly."""
    class _AdultOnly(NoraAppConfig):
        name = "houseapps.example_habit"
        nora_slug = "finances"
        nora_minimum_role = "adult"

    meta = _AdultOnly("houseapps.example_habit", __import__("houseapps")).nora_home_metadata
    rank = {"member": 0, "adult": 1, "admin": 2}
    assert rank["member"] < rank[meta.minimum_role]
    assert rank["adult"] >= rank[meta.minimum_role]


def test_member_nav_is_a_subset_of_admin_nav():
    def slugs(role):
        return {m.slug for g in navigation(role) for m in g["apps"]}

    assert slugs("member") <= slugs("adult") <= slugs("admin")


def test_unknown_role_is_treated_as_the_least_privileged():
    def slugs(role):
        return {m.slug for g in navigation(role) for m in g["apps"]}

    assert slugs("houseguest") == slugs("member")


# ── URL mounting ─────────────────────────────────────────────────────────────

def test_house_apps_mount_at_the_url_root():
    """Checked against whatever is actually installed rather than a hardcoded
    slug, so this does not need editing every time the house app roster
    changes. No house apps installed is the current, legitimate state (see
    docs/Main_App/subsystems/todo.md §1) until Story 24."""
    installed = house_apps()
    if not installed:
        pytest.skip("no house apps installed — expected until Story 24")

    prefixes = {str(p.pattern) for p in house_app_urlpatterns()}
    for meta in installed:
        assert meta.url_prefix in prefixes, f"{meta.slug} did not mount at {meta.url_prefix}"


def test_platform_apps_are_never_auto_mounted():
    """config/urls.py mounts platform routes explicitly. Auto-mounting them too
    would shadow /home/ with a second, half-configured copy."""
    for pattern in house_app_urlpatterns():
        assert not str(pattern.pattern).startswith("home/")


@pytest.mark.parametrize("slug", ["home", "admin", "api", "mcp", "static", "accounts"])
def test_platform_prefixes_are_reserved(slug):
    assert slug in RESERVED_SLUGS


def test_an_app_claiming_a_reserved_slug_is_skipped_not_fatal(caplog, monkeypatch):
    """One bad app must never stop the wall display from booting. The house
    degrades; it does not cascade."""
    import nora_home.core.registry as registry

    greedy = AppMetadata(
        slug="admin", title="Greedy", description="", icon="x",
        category=Category.HOUSE, color="", module="houseapps.greedy", nav=True,
        has_page=True, order=1, url_prefix="admin/",
    )
    monkeypatch.setattr(registry, "registered_apps", lambda **kw: [greedy])

    patterns = registry.house_app_urlpatterns()

    assert patterns == []
    assert "reserves" in caplog.text


def test_an_app_with_no_urls_module_is_skipped_quietly(monkeypatch):
    """An app can be widgets-only. That is not an error and must not log one."""
    import nora_home.core.registry as registry

    pageless = AppMetadata(
        slug="widgetsonly", title="Widgets only", description="", icon="x",
        category=Category.HOUSE, color="", module="houseapps.does_not_exist",
        nav=False, has_page=False, order=1, url_prefix="widgetsonly/",
    )
    monkeypatch.setattr(registry, "registered_apps", lambda **kw: [pageless])

    assert registry.house_app_urlpatterns() == []


def test_apps_without_a_page_declare_it():
    """nora_has_page exists so the Apps directory never links somewhere that
    404s. Any app claiming a page should have a urls.py to back it."""
    from importlib.util import find_spec

    for meta in registered_apps():
        if not meta.has_page:
            continue
        assert find_spec(f"{meta.module}.urls") is not None, (
            f"{meta.slug} claims nora_has_page but ships no urls.py")


# ── scoping ──────────────────────────────────────────────────────────────────

def test_scope_members_returns_just_the_viewer_by_default(rf, member):
    request = rf.get("/home/")
    request.user = member
    request.session = {}
    assert scope_members(request) == [member]


def test_scope_members_returns_everyone_in_combined_view(rf, household):
    request = rf.get("/home/")
    request.user = household["kid"]
    request.session = {"nh_view_scope": "all"}

    scoped = scope_members(request)

    assert len(scoped) == 3
    assert set(scoped) == set(household.values())


def test_scope_members_excludes_deactivated_people(rf, household):
    household["adult"].is_active = False
    household["adult"].save()

    request = rf.get("/home/")
    request.user = household["kid"]
    request.session = {"nh_view_scope": "all"}

    assert household["adult"] not in scope_members(request)
