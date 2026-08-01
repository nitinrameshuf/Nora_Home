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


@login_required
def home(request):
    """The home screen: this person's chosen visualizations, on their own grid."""
    role = getattr(request.user, "role", "member")
    layout = DashboardLayout.for_member(request.user)
    available = all_widgets(role)
    by_key = {widget.key: widget for widget in available}

    placed = []
    for item in layout.items:
        widget = by_key.get(item.get("key", ""))
        if widget is None or not widget.is_visible(request):
            continue  # app uninstalled or hidden — skip, do not delete the entry
        placed.append({
            "x": item.get("x", 0), "y": item.get("y", 0),
            "w": item.get("w", widget.default_size[0]),
            "h": item.get("h", widget.default_size[1]),
            "widget": widget.payload(request),
        })

    return render(request, "dashboard/home.html", {
        "layout": layout,
        "placed_json": json.dumps(placed),
        "catalog": [w.as_menu_entry() for w in available],
        "catalog_json": json.dumps([w.as_menu_entry() for w in available]),
        "page_title": "Home",
    })


@login_required
def widget_data(request, key: str):
    """Fresh data for one widget — used by auto-refresh and by the wall display."""
    widget = get_widget(key, getattr(request.user, "role", "member"))
    if widget is None:
        return JsonResponse({"error": "no such widget"}, status=404)
    return JsonResponse(widget.payload(request))


@login_required
def catalog(request):
    """Everything installable on the home screen, for the picker."""
    widgets = all_widgets(getattr(request.user, "role", "member"))
    return JsonResponse({"widgets": [w.as_menu_entry() for w in widgets]})


@login_required
@require_POST
def save_layout(request):
    """Persist a drag-and-drop rearrangement.

    Positions are validated rather than trusted: a malformed payload from a stale
    tab should not be able to write nonsense that breaks everyone's home screen.
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

    known = {w.key for w in all_widgets(getattr(request.user, "role", "member"))}
    cleaned = []
    for item in raw_items:
        if not isinstance(item, dict) or item.get("key") not in known:
            continue
        cleaned.append({
            "key": item["key"],
            "x": _clamp(item.get("x"), 0, 11),
            "y": _clamp(item.get("y"), 0, 200),
            "w": _clamp(item.get("w"), 1, 12),
            "h": _clamp(item.get("h"), 1, 12),
        })

    layout = DashboardLayout.for_member(request.user)
    layout.items = cleaned
    layout.save(update_fields=["items", "updated_at"])
    return JsonResponse({"ok": True, "count": len(cleaned)})


def _clamp(value, low: int, high: int) -> int:
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        return low
