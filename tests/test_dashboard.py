"""
The home screen: widgets, layouts, and the save endpoint behind drag-and-drop.

Two rules from CLAUDE.md are load-bearing here. "Widgets return data, not HTML"
is what keeps every chart in the house looking like one system. And a widget that
raises must render as "unavailable" rather than 500 — the home screen is what the
24" wall iframes, so one broken app must not blank the wall.

The save endpoint gets the most attention: it takes JSON from the browser, and
"Add a widget" has already broken once in a way that looked like it worked (the
POST 403'd, but fetch() does not reject on a non-2xx, so the page reloaded anyway
and the failure was invisible).
"""

from __future__ import annotations

import json

import pytest
from django.urls import reverse

from nora_home.core.registry import all_widgets, get_widget
from nora_home.dashboard.models import STARTER_LAYOUT, DashboardLayout
from nora_home.dashboard.widgets import (
    GRID_COLUMNS,
    MAX_ROWS,
    ChartWidget,
    ListWidget,
    StatWidget,
    Widget,
    load_widget,
)
from nora_home.dashboard.views import MAX_ITEMS, _layout_for, _widgets_for

pytestmark = pytest.mark.django_db


# ── layouts ──────────────────────────────────────────────────────────────────

def test_a_new_member_gets_the_starter_layout(member):
    layout = DashboardLayout.for_member(member)

    assert layout.items == STARTER_LAYOUT


def test_a_members_layout_is_created_once(member):
    DashboardLayout.for_member(member)
    DashboardLayout.for_member(member)

    assert DashboardLayout.objects.filter(member=member).count() == 1


def test_layouts_are_per_person(member, adult):
    mine = DashboardLayout.for_member(member)
    mine.items = [{"key": "todo.OpenLoadWidget", "x": 0, "y": 0, "w": 12, "h": 4}]
    mine.save()

    assert DashboardLayout.for_member(adult).items == STARTER_LAYOUT


def test_the_wall_has_its_own_layout(member):
    """"so the living-room screen does not inherit whatever someone last dragged
    around on their phone"."""
    DashboardLayout.for_member(member).items = []

    assert DashboardLayout.for_wall().member is None
    assert DashboardLayout.for_wall().surface == DashboardLayout.Surface.WALL


def test_the_shared_layout_is_distinct_from_the_wall():
    """The "Everyone" switcher tile and the 24" wall are different surfaces that
    happened to share a model — keeping them apart is deliberate."""
    assert DashboardLayout.for_shared().pk != DashboardLayout.for_wall().pk


# ── which layout a request resolves to (Story 39, §11.2) ────────────────────

def test_the_wall_surface_gets_the_walls_layout_regardless_of_session(rf, member):
    """However the wall's browser happens to be signed in, it must never show
    a person's own dragged-around screen — that is the whole point of the
    layout existing separately at all."""
    request = rf.get("/home/")
    request.user = member
    request.nh_surface = "wall"
    request.session = {"nh_view_scope": "self"}

    assert _layout_for(request).surface == DashboardLayout.Surface.WALL


def test_wall_view_scope_also_resolves_to_the_walls_layout(rf, adult):
    """Editing from a phone: no wall surface, but the session says "I am
    arranging the wall's screen right now"."""
    request = rf.get("/home/")
    request.user = adult
    request.nh_surface = "desktop"
    request.session = {"nh_view_scope": "wall"}

    assert _layout_for(request).surface == DashboardLayout.Surface.WALL


def test_everyone_scope_still_works_when_not_on_the_wall(rf, adult):
    request = rf.get("/home/")
    request.user = adult
    request.nh_surface = "desktop"
    request.session = {"nh_view_scope": "all"}

    assert _layout_for(request).surface == DashboardLayout.Surface.SHARED


def test_the_default_is_still_a_persons_own_layout(rf, adult):
    request = rf.get("/home/")
    request.user = adult
    request.nh_surface = "desktop"
    request.session = {}

    layout = _layout_for(request)

    assert layout.surface == DashboardLayout.Surface.PERSONAL
    assert layout.member == adult


# ── the picker respects wall_safe (§11.2) ────────────────────────────────────

def test_a_non_wall_safe_widget_is_offered_off_the_wall(rf, adult, monkeypatch):
    class RoomSensitive:
        key = "test.RoomSensitive"
        wall_safe = False

    class Ordinary:
        key = "test.Ordinary"
        wall_safe = True

    monkeypatch.setattr("nora_home.dashboard.views.all_widgets",
                        lambda role: [RoomSensitive(), Ordinary()])

    personal = _widgets_for(_FakeRequest(adult), DashboardLayout.for_member(adult))
    on_wall = _widgets_for(_FakeRequest(adult), DashboardLayout.for_wall())

    assert {w.key for w in personal} == {"test.RoomSensitive", "test.Ordinary"}
    assert {w.key for w in on_wall} == {"test.Ordinary"}


class _FakeRequest:
    """Just enough of a request for _widgets_for(), which only reads .user."""
    def __init__(self, user):
        self.user = user


def test_the_wall_cannot_be_given_a_non_wall_safe_widget_by_a_direct_post(
        client, adult, monkeypatch):
    """The picker hiding it is not the actual guarantee — save_layout() must
    refuse it even if something posts the key directly, the same "validated,
    not trusted" rule already applied to positions."""
    class RoomSensitive:
        key = "test.NotForTheWall"
        wall_safe = False
        title = "Room-sensitive"

    monkeypatch.setattr("nora_home.dashboard.views.all_widgets",
                        lambda role: [RoomSensitive()])
    client.force_login(adult)
    client.post(reverse("accounts:switch_to_wall"))

    response = client.post("/home/dashboard/layout/",
                           data=json.dumps({"items": [
                               {"key": "test.NotForTheWall", "x": 0, "y": 0, "w": 4, "h": 4}]}),
                           content_type="application/json")

    assert response.status_code == 200
    assert DashboardLayout.for_wall().items == []


def test_the_wall_iframe_gets_the_walls_layout_over_real_http(client, adult):
    """End to end through the real request cycle, not the unit-level
    _layout_for() calls above: the exact headers Chromium sends when the
    wall's iframe loads /home/, and the exact page the browser gets back."""
    client.force_login(adult)
    key = all_widgets("admin")[0].key
    wall_layout = DashboardLayout.for_wall()
    wall_layout.items = [{"key": key, "x": 0, "y": 0, "w": 4, "h": 4}]
    wall_layout.save()

    response = client.get(
        "/home/", HTTP_SEC_FETCH_DEST="iframe",
        HTTP_REFERER="https://nora.home/home/displays/wall/")

    assert response.status_code == 200
    assert response.context["layout"].surface == DashboardLayout.Surface.WALL


def test_saving_while_in_wall_scope_writes_to_the_walls_layout(client, adult):
    client.force_login(adult)
    client.post(reverse("accounts:switch_to_wall"))
    key = all_widgets("admin")[0].key

    response = client.post("/home/dashboard/layout/",
                           data=json.dumps({"items": [
                               {"key": key, "x": 0, "y": 0, "w": 4, "h": 4}]}),
                           content_type="application/json")

    assert response.status_code == 200
    assert key in DashboardLayout.for_wall().keys()
    # And critically not the signer's own personal screen.
    assert key not in DashboardLayout.for_member(adult).keys()


def test_keys_lists_only_placed_widgets(member):
    layout = DashboardLayout.for_member(member)
    layout.items = [{"key": "a.B", "x": 0}, {"no": "key"}, {"key": ""}]

    assert layout.keys() == ["a.B"]


# ── the widget contract ──────────────────────────────────────────────────────

def test_every_registered_widget_loads():
    """A typo in an app's nora_widgets would otherwise only show up as a widget
    quietly missing from the picker."""
    assert all_widgets("admin"), "no widgets are registered at all"


def test_every_widget_has_a_key_and_a_title():
    for widget in all_widgets("admin"):
        assert widget.key and "." in widget.key, f"{widget} has a malformed key"
        assert widget.title, f"{widget.key} has no title"


def test_every_widget_fits_the_grid():
    for widget in all_widgets("admin"):
        width, height = widget.default_size
        assert 1 <= width <= GRID_COLUMNS, f"{widget.key} is {width} columns wide"
        assert 1 <= height <= MAX_ROWS


def test_widget_keys_are_unique():
    keys = [w.key for w in all_widgets("admin")]

    assert len(keys) == len(set(keys)), "two widgets share a registry key"


def test_get_widget_finds_one_by_key():
    known = all_widgets("admin")[0]

    assert get_widget(known.key, "admin").key == known.key


def test_get_widget_returns_none_for_an_unknown_key():
    assert get_widget("nope.NotAWidget", "admin") is None


def test_menu_entries_carry_what_the_picker_needs():
    for widget in all_widgets("admin"):
        entry = widget.as_menu_entry()
        assert set(entry) >= {"key", "title", "app", "kind", "w", "h"}


def test_a_widget_that_raises_renders_as_unavailable(rf, member):
    """One app's bad query must not blank the wall (CLAUDE.md §6)."""
    class Broken(StatWidget):
        title = "Broken"

        def stat(self, request):
            raise RuntimeError("bad query")

    request = rf.get("/home/")
    request.user = member

    payload = Broken().payload(request)

    assert payload["kind"] == "error"
    assert "could not load" in payload["message"]


def test_a_working_widget_returns_data_not_html(rf, member):
    """The house theme is applied centrally; a widget returning its own markup
    would opt out of it."""
    class Volume(ChartWidget):
        title = "Volume"

        def option(self, request):
            return {"series": [{"type": "bar", "data": [1, 2, 3]}]}

    request = rf.get("/home/")
    request.user = member

    payload = Volume().payload(request)

    assert payload["kind"] == "chart"
    assert payload["option"]["series"][0]["data"] == [1, 2, 3]
    assert "html" not in payload


def test_a_list_widget_carries_its_empty_message(rf, member):
    class Empty(ListWidget):
        title = "Nothing"
        empty_message = "All clear."

        def rows(self, request):
            return []

    request = rf.get("/home/")
    request.user = member

    payload = Empty().payload(request)

    assert payload["rows"] == []
    assert payload["empty_message"] == "All clear."


def test_load_widget_rejects_a_class_that_is_not_a_widget():
    assert load_widget("nora_home.accounts.models.HouseMember") is None


def test_load_widget_returns_none_for_a_missing_import():
    assert load_widget("nope.nothing.AtAll") is None


def test_load_widget_clamps_an_out_of_range_size():
    """A widget declaring 40 columns would otherwise push everything else off
    the grid on every screen that shows it."""
    class TooWide(Widget):
        default_size = (40, 99)

    module = __name__
    import sys
    setattr(sys.modules[module], "TooWide", TooWide)

    widget = load_widget(f"{module}.TooWide")

    assert widget.default_size == (GRID_COLUMNS, MAX_ROWS)


# ── the home page ────────────────────────────────────────────────────────────

def test_the_home_page_renders(client, adult):
    client.force_login(adult)

    response = client.get("/home/")

    assert response.status_code == 200


def test_the_home_page_needs_a_signed_in_member(client):
    assert client.get("/home/").status_code == 302


def test_an_unresolvable_widget_is_skipped_not_deleted(client, adult):
    """"A key that no longer resolves is skipped at render time rather than
    deleted, so reinstalling the app restores the layout"."""
    layout = DashboardLayout.for_member(adult)
    layout.items = [{"key": "uninstalled.Widget", "x": 0, "y": 0, "w": 4, "h": 4}]
    layout.save()
    client.force_login(adult)

    response = client.get("/home/")

    assert response.status_code == 200
    layout.refresh_from_db()
    assert layout.items[0]["key"] == "uninstalled.Widget", "the entry was destroyed"


# ── saving a layout ──────────────────────────────────────────────────────────

def _save(client, items):
    return client.post("/home/dashboard/layout/", data=json.dumps({"items": items}),
                       content_type="application/json")


def test_saving_a_layout_persists_it(client, adult):
    client.force_login(adult)
    key = all_widgets("admin")[0].key

    response = _save(client, [{"key": key, "x": 1, "y": 2, "w": 4, "h": 3}])

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert DashboardLayout.for_member(adult).items == [
        {"key": key, "x": 1, "y": 2, "w": 4, "h": 3}]


def test_adding_a_widget_actually_saves_it(client, adult):
    """"Add a widget" broke once in a way that looked like it worked: the POST
    403'd, fetch() did not reject on the non-2xx, and the page reloaded anyway.
    This asserts the write landed, not just that the request was accepted."""
    client.force_login(adult)
    existing = DashboardLayout.for_member(adult).items
    new_key = all_widgets("admin")[-1].key
    items = [*existing, {"key": new_key, "x": 0, "y": 40, "w": 4, "h": 3}]

    _save(client, items)

    assert new_key in DashboardLayout.for_member(adult).keys()


def test_an_unknown_widget_key_is_dropped(client, adult):
    """A stale tab must not be able to write a key nobody can render."""
    client.force_login(adult)

    _save(client, [{"key": "malicious.Widget", "x": 0, "y": 0, "w": 4, "h": 4}])

    assert DashboardLayout.for_member(adult).items == []


def test_positions_are_clamped_to_the_grid(client, adult):
    client.force_login(adult)
    key = all_widgets("admin")[0].key

    _save(client, [{"key": key, "x": 999, "y": -5, "w": 99, "h": 0}])

    item = DashboardLayout.for_member(adult).items[0]
    assert item["x"] == 11
    assert item["y"] == 0
    assert item["w"] == 12
    assert item["h"] == 1


def test_non_numeric_positions_do_not_break_the_save(client, adult):
    client.force_login(adult)
    key = all_widgets("admin")[0].key

    response = _save(client, [{"key": key, "x": "left", "y": None, "w": [], "h": {}}])

    assert response.status_code == 200


def test_a_malformed_body_is_rejected(client, adult):
    client.force_login(adult)

    response = client.post("/home/dashboard/layout/", data="not json",
                           content_type="application/json")

    assert response.status_code == 400


def test_items_must_be_a_list(client, adult):
    client.force_login(adult)

    response = client.post("/home/dashboard/layout/",
                           data=json.dumps({"items": {"key": "x"}}),
                           content_type="application/json")

    assert response.status_code == 400


def test_an_absurd_number_of_widgets_is_refused(client, adult):
    client.force_login(adult)
    key = all_widgets("admin")[0].key

    response = _save(client, [{"key": key, "x": 0, "y": i, "w": 1, "h": 1}
                              for i in range(MAX_ITEMS + 1)])

    assert response.status_code == 400


def test_saving_requires_a_signed_in_member(client):
    assert _save(client, []).status_code == 302


def test_saving_requires_post(client, adult):
    client.force_login(adult)

    assert client.get("/home/dashboard/layout/").status_code == 405


def test_in_everyone_scope_the_shared_layout_is_saved(client, adult):
    """Rearranging the combined view must not silently overwrite the personal
    home screen of whoever happens to be signed in behind it."""
    client.force_login(adult)
    session = client.session
    session["nh_view_scope"] = "all"
    session.save()
    key = all_widgets("admin")[0].key

    _save(client, [{"key": key, "x": 0, "y": 0, "w": 4, "h": 4}])

    assert DashboardLayout.for_shared().keys() == [key]
    assert DashboardLayout.for_member(adult).items == STARTER_LAYOUT


# ── widget data endpoint ─────────────────────────────────────────────────────

def test_widget_data_returns_a_payload(client, adult):
    from django.urls import reverse

    client.force_login(adult)
    key = all_widgets("admin")[0].key

    response = client.get(reverse("dashboard:widget_data", args=[key]))

    assert response.status_code == 200
    assert response.json()["key"] == key


def test_widget_data_404s_for_an_unknown_key(client, adult):
    from django.urls import reverse

    client.force_login(adult)

    response = client.get(reverse("dashboard:widget_data", args=["nope.NotReal"]))

    assert response.status_code == 404


def test_the_catalog_lists_every_widget(client, adult):
    client.force_login(adult)

    payload = client.get("/home/dashboard/catalog/").json()

    assert len(payload["widgets"]) == len(all_widgets("admin"))
