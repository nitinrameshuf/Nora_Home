from __future__ import annotations

import json
import logging

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from nora_home.core.registry import all_widgets, get_widget
from nora_home.dashboard.models import DashboardLayout

logger = logging.getLogger(__name__)

MAX_ITEMS = 40


def _layout_for(request) -> DashboardLayout:
    """Which grid this request should see: the wall's own (never a member's
    personal one, however the wall happens to be signed in — see
    DashboardLayout's own docstring on why), then "Everyone" scope, then the
    signed-in person's. Checked in that order because the wall surface is a
    property of the *request*, while view-scope is a property of the
    *session* — a family member editing "Everyone" from their phone must not
    accidentally start editing the wall's layout if they later happen to view
    it through the wall itself.
    """
    if request.session.get("nh_view_scope") == "wall" or request.nh_surface == "wall":
        return DashboardLayout.for_wall()
    if request.session.get("nh_view_scope") == "all":
        return DashboardLayout.for_shared()
    return DashboardLayout.for_member(request.user)


def _widgets_for(request, layout: DashboardLayout) -> list:
    """The catalog this layout may draw from — every widget, unless this is
    the wall's own layout, in which case only ones that declared themselves
    `wall_safe` (§11.2). Applied everywhere a widget key can enter a layout
    (here, `catalog()`, and `save_layout()`'s validation set) so this is an
    actual constraint and not just a picker that politely hides the rest —
    the same "validated, not trusted" rule save_layout() already applies to
    positions.
    """
    role = getattr(request.user, "role", "member")
    widgets = all_widgets(role)
    if layout.surface == DashboardLayout.Surface.WALL:
        widgets = [w for w in widgets if w.wall_safe]
    return widgets


@login_required
def home(request):
    """The home screen: this person's chosen visualizations, on their own
    grid — or, in "Everyone" scope, the one grid the whole house shares — or,
    on the wall itself, the layout curated for it specifically (§11.2:
    "the living-room screen does not inherit whatever someone last dragged
    around on their phone")."""
    layout = _layout_for(request)
    available = _widgets_for(request, layout)
    by_key = {widget.key: widget for widget in available}

    placed = []
    for item in layout.items:
        widget = by_key.get(item.get("key", ""))
        if widget is None or not widget.is_visible(request):
            continue  # app uninstalled or hidden — skip, do not delete the entry
        # The list's order *is* the layout — CSS grid places the tiles — so the
        # only thing to carry per item is which size it was set to.
        placed.append({"widget": widget.payload(request, item.get("size", ""))})

    return render(request, "dashboard/home.html", {
        "layout": layout,
        "placed_json": json.dumps(placed),
        "catalog": [w.as_menu_entry() for w in available],
        "catalog_json": json.dumps([w.as_menu_entry() for w in available]),
        "page_title": "Home",
    })


@login_required
def widget_data(request, key: str):
    """Fresh data for one widget — used by auto-refresh and by the wall display.

    `?size=` matters here rather than being cosmetic: a list at M is a readout
    and at L is four rows, so refreshing without the caller's current size
    would quietly redraw the tile as a different variant.
    """
    widget = get_widget(key, getattr(request.user, "role", "member"))
    if widget is None:
        return JsonResponse({"error": "no such widget"}, status=404)
    return JsonResponse(widget.payload(request, request.GET.get("size", "")))


@login_required
def catalog(request):
    """Everything installable on the home screen, for the picker — narrowed to
    wall_safe widgets when the session is currently editing the wall's own
    layout, so the picker never offers something save_layout() would refuse."""
    widgets = _widgets_for(request, _layout_for(request))
    return JsonResponse({"widgets": [w.as_menu_entry() for w in widgets]})


@login_required
@require_POST
def save_layout(request):
    """Persist a rearrangement — the order of the list, and each item's size.

    Both are validated rather than trusted: a malformed payload from a stale tab
    should not be able to write nonsense that breaks everyone's home screen.
    """
    try:
        payload = json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return JsonResponse({"ok": False, "error": "body must be JSON"}, status=400)

    raw_items = payload.get("items")
    if not isinstance(raw_items, list):
        return JsonResponse({"ok": False, "error": "items must be a list"}, status=400)
    if len(raw_items) > MAX_ITEMS:
        return JsonResponse({"ok": False, "error": "too many widgets"}, status=400)

    layout = _layout_for(request)
    by_key = {w.key: w for w in _widgets_for(request, layout)}
    cleaned = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        widget = by_key.get(item.get("key"))
        if widget is None:
            continue
        # resolve_size() rather than a bare membership test: it is the same
        # fallback the renderer uses, so a size the widget does not offer is
        # stored as what will actually be drawn, instead of being persisted
        # and silently re-resolved on every page load.
        cleaned.append({"key": item["key"],
                        "size": widget.resolve_size(item.get("size", ""))})

    layout.items = cleaned
    layout.save(update_fields=["items", "updated_at"])
    return JsonResponse({"ok": True, "count": len(cleaned)})
