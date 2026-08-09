"""
The house's component library — Story 45.

Eleven components (`docs/User/dashboard/nora_home_dashboard.html`, Story 45):
Card, Stat, List, Chart, Toolbar, EmptyState, Sheet, Tile, Ring, Key, Picker.
Every one of them is grounded in `docs/Main_App/ui-overhaul-mockup.html`'s own
`@layer comp` / `@layer work` / `@layer kiosk` / `@layer phone` — copied, not
reasoned about independently, per CLAUDE.md §4 ("the mockup is the UI reference").

Two component names needed a decision the mockup does not spell out on its own,
and both are written down here rather than left implicit:

Tile vs. Card
    In the mockup's actual markup there is one element (`.card`) that both
    places itself on the 12-column grid (`--c`/`--r`, from `.bento > .card`)
    *and* carries the header/body chrome. The OLD dashboard.js already drew
    this exact seam, just under different names: `dash-tile-wrap` (the grid
    cell — position, size, drag handle) and `dash-tile` (`dash-tile__head`/
    `__title`/`__sub`/`__tools`/`__body` — the chrome inside it). This library
    keeps that seam and gives it the story's names: {% nh_tile %} is the grid
    cell, {% nh_card %} is the chrome. A tile normally contains exactly one
    card; a card can also stand alone (inside a Sheet, for instance) with no
    tile around it at all.

Chart
    Stays a thin holder — `{% nh_chart %}` wraps a `{% nh_card %}` around a
    `[data-nh-chart]` div and nothing more. `nora_home/dashboard/widgets.py`'s
    contract ("Widgets return data, not HTML") is deliberately untouched here;
    what actually draws the ECharts instance into that div is
    `assets/js/nh-charts.js`, which Story 45 does not touch — see CLAUDE.md
    §4, Phase 8: "nh-charts.js's house theme goes with it [eventually]... but
    the [data] contract holds."

Nothing in the house's real templates loads this yet. /home/styleguide/
renders every component in every state so it can be reviewed and proven before
anything is rewired to use it — the same "prove it standalone first" shape as
Story 43's build pipeline and Story 44's token layer.
"""

from __future__ import annotations

import math

from django import template
from django.template.base import FilterExpression, Node
from django.template.loader import render_to_string
from django.utils.safestring import mark_safe

register = template.Library()


# ── shared kwargs parsing for the block tags ──────────────────────────────
#
# Django's inclusion_tag only covers leaf components (no nested template
# content), so the four wrapping components (Card, Tile, Sheet, Toolbar) are
# hand-written Node subclasses instead. All four take only `key=value`
# arguments, so one parser serves them all.

def _parse_kwargs(parser, bits: list[str]) -> dict[str, FilterExpression]:
    kwargs = {}
    for bit in bits:
        if "=" not in bit:
            raise template.TemplateSyntaxError(
                f"expected key=value, got {bit!r} — every argument to an nh_* "
                "tag is named")
        key, _, value = bit.partition("=")
        kwargs[key] = parser.compile_filter(value)
    return kwargs


def _resolve(kwargs: dict[str, FilterExpression], context) -> dict:
    return {key: expr.resolve(context) for key, expr in kwargs.items()}


def _block_tag(tag_name: str, node_class: type[Node]):
    """Registers `{% tag_name k=v ... %}...{% endtag_name %}` for a Node
    subclass whose __init__ takes (nodelist, **kwargs)."""

    def compile_tag(parser, token):
        bits = token.split_contents()[1:]
        kwargs = _parse_kwargs(parser, bits)
        nodelist = parser.parse((f"end{tag_name}",))
        parser.delete_first_token()
        return node_class(nodelist, **kwargs)

    register.tag(tag_name, compile_tag)


# ── Card ────────────────────────────────────────────────────────────────
#
# templates/nh/card.html. `title` is the only thing every card needs; the
# rest are optional per the mockup's .card-h (subtitle, a right-aligned
# `source` label, or a `tools` slot for a toolbar — those two are mutually
# exclusive in the mockup's own markup, so only one renders here too).

class CardNode(Node):
    def __init__(self, nodelist, **kwargs):
        self.nodelist = nodelist
        self.kwargs = kwargs

    def render(self, context):
        opts = _resolve(self.kwargs, context)
        body = self.nodelist.render(context)
        return render_to_string("nh/card.html", {
            "title": opts.get("title", ""),
            "subtitle": opts.get("subtitle", ""),
            "source": opts.get("source", ""),
            "status": opts.get("status", ""),  # "" | ok | warn | crit — tints the card
            "body_class": opts.get("body_class", ""),
            "body": mark_safe(body),
        })


_block_tag("nh_card", CardNode)


# ── Tile ────────────────────────────────────────────────────────────────
#
# templates/nh/tile.html. The grid cell: size in {S, M, L, XL}, matching the
# mockup's SIZES table exactly (`const SIZES = { S:{c:3,r:1}, M:{c:6,r:1},
# L:{c:6,r:2}, XL:{c:12,r:1} }`). Only meaningful inside a `.bento` grid.

TILE_SIZES = {"S": (3, 1), "M": (6, 1), "L": (6, 2), "XL": (12, 1)}


class TileNode(Node):
    def __init__(self, nodelist, **kwargs):
        self.nodelist = nodelist
        self.kwargs = kwargs

    def render(self, context):
        opts = _resolve(self.kwargs, context)
        size = opts.get("size", "M")
        cols, rows = TILE_SIZES.get(size, TILE_SIZES["M"])
        body = self.nodelist.render(context)
        return render_to_string("nh/tile.html", {
            "size": size, "cols": cols, "rows": rows,
            "body": mark_safe(body),
        })


_block_tag("nh_tile", TileNode)


# ── Sheet ───────────────────────────────────────────────────────────────
#
# templates/nh/sheet.html. The modal form surface — `.scrim`/`.sheet`/`.h3`
# from the mockup. `wide=1` is the mockup's `.sheet.wide` (task-form-sized
# rather than the default confirm-sized sheet). Foot buttons are the block's
# own content, not a separate slot — matches how every sheet in the mockup
# ends with a plain `.sheet-foot` div the caller writes directly.

class SheetNode(Node):
    def __init__(self, nodelist, **kwargs):
        self.nodelist = nodelist
        self.kwargs = kwargs

    def render(self, context):
        opts = _resolve(self.kwargs, context)
        body = self.nodelist.render(context)
        return render_to_string("nh/sheet.html", {
            "title": opts.get("title", ""),
            "wide": bool(opts.get("wide", False)),
            "body": mark_safe(body),
        })


_block_tag("nh_sheet", SheetNode)


# ── Toolbar ─────────────────────────────────────────────────────────────
#
# templates/nh/toolbar.html. The mockup's `.card-h .tools` cluster, pulled out
# on its own so it can also sit outside a card header — the board's filter
# row and the reporting page's control strip both use a bare toolbar today.

class ToolbarNode(Node):
    def __init__(self, nodelist, **kwargs):
        self.nodelist = nodelist
        self.kwargs = kwargs

    def render(self, context):
        opts = _resolve(self.kwargs, context)
        body = self.nodelist.render(context)
        return render_to_string("nh/toolbar.html", {
            "align": opts.get("align", "end"),  # "end" | "start"
            "body": mark_safe(body),
        })


_block_tag("nh_toolbar", ToolbarNode)


# ── Stat, List, Chart, EmptyState, Ring, Key, Badge, Chip, Button ─────────
#
# Leaves: no nested content, so plain inclusion_tag is enough for each.

@register.inclusion_tag("nh/stat.html")
def nh_stat(value, label="", unit="", delta=None, status="", spark=None):
    """`nora_home/dashboard/widgets.py`'s StatWidget.stat() shape exactly:
    {value, label, unit, delta, status, spark} — this tag is that dict's
    renderer, not a separate design."""
    points = _sparkline_points(spark) if spark else None
    return {"value": value, "label": label, "unit": unit, "delta": delta,
             "status": status, "spark_points": points}


def _sparkline_points(values: list[float]) -> str:
    """A bare polyline, not a chart — no ECharts instance for eight numbers
    under a stat. 64x20 viewBox, matching the tightest card the mockup draws
    a stat inside."""
    if len(values) < 2:
        return ""
    lo, hi = min(values), max(values)
    span = (hi - lo) or 1
    step = 64 / (len(values) - 1)
    pts = [
        f"{i * step:.1f},{20 - ((v - lo) / span) * 18 - 1:.1f}"
        for i, v in enumerate(values)
    ]
    return " ".join(pts)


@register.inclusion_tag("nh/list.html")
def nh_list(rows, empty_message="Nothing here."):
    """`ListWidget.rows()`'s shape: [{title, meta, status, url, action_url}].
    `status` of "late" tints the leading marker and the meta text; "done"
    strikes the row — both straight from the mockup's `.row`/`.ck`/`.d.late`."""
    return {"rows": rows or [], "empty_message": empty_message}


@register.inclusion_tag("nh/chart.html")
def nh_chart(option, title="", subtitle="", key=""):
    """A holder, not a renderer — see the module docstring. `option` is
    whatever a ChartWidget.option() returned; nh-charts.js reads it from the
    div's data attribute exactly as it does today.

    `option_json` is NOT mark_safe: it lands inside a double-quoted HTML
    attribute, and Django's normal auto-escaping is what turns an option
    dict's own `"` characters into `&quot;` so they cannot terminate the
    attribute early. Marking it safe here was tried and breaks the attribute
    the first time an option value contains a quote.
    """
    import json

    return {"title": title, "subtitle": subtitle, "key": key,
            "option_json": json.dumps(option or {})}


@register.inclusion_tag("nh/empty.html")
def nh_empty(title="Nothing here", message=""):
    return {"title": title, "message": message}


@register.inclusion_tag("nh/ring.html")
def nh_ring(pct, big="", small="", color="var(--arc-400)"):
    """The concentric ring gauge, math ported verbatim from the mockup's own
    `ring()` (R=42, C=2*pi*R, dashoffset = C*(1-pct/100), rotated -90deg so
    the gauge starts at 12 o'clock)."""
    pct = max(0, min(100, float(pct)))
    radius = 42
    circumference = 2 * math.pi * radius
    offset = circumference * (1 - pct / 100)
    return {"pct": pct, "big": big, "small": small, "color": color,
            "radius": radius, "circumference": f"{circumference:.3f}",
            "offset": f"{offset:.3f}"}


@register.inclusion_tag("nh/key.html")
def nh_key(label, hue="var(--arc-500)", number="", href="", action="", value="",
           wide=False):
    """The kiosk's illuminated square key (`.hkey`). `hue` sets `--key`, the
    custom property the mockup's `.hkey`/`.led` both read — see KEY_HUES in
    the mockup for the palette a bank of keys cycles through."""
    return {"label": label, "hue": hue, "number": number, "href": href,
            "action": action, "value": value, "wide": wide}


@register.inclusion_tag("nh/badge.html")
def nh_badge(text, status="ok"):
    return {"text": text, "status": status}


@register.inclusion_tag("nh/chip.html")
def nh_chip(label, action="", value="", pressed=False):
    return {"label": label, "action": action, "value": value, "pressed": pressed}


@register.inclusion_tag("nh/button.html")
def nh_button(label, variant="", action="", value="", href="", kbd="", button_type="button"):
    """`variant`: "" (default) | "pri" | "ghost" — the mockup's `.btn`/
    `.btn.pri`/`.btn.ghost`."""
    return {"label": label, "variant": variant, "action": action,
            "value": value, "href": href, "kbd": kbd, "button_type": button_type}


# ── Picker ──────────────────────────────────────────────────────────────
#
# templates/nh/picker.html + assets/js/nh-picker.js. One component on two
# axes — see nh-picker.js's own docstring for the physics (capture-phase
# scroll listener, debounce, the programmatic-centring flag) ported from the
# mockup's `.vsel-*` (kiosk, vertical) / `.ph-*` (phone, horizontal).

@register.inclusion_tag("nh/picker.html")
def nh_picker(items, active="", orientation="vertical"):
    """`items`: [{slug, title, icon}]. `orientation`: "vertical" (the kiosk's
    app scroller) | "horizontal" (the phone's app rail) — same control,
    same behaviour, rotated."""
    return {"items": items or [], "active": active, "orientation": orientation}
