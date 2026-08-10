"""
Widgets — the visualizations apps offer to the home screen.

The home page is a grid the family arranges themselves: each person picks widgets
from any installed app, drags them where they want, and that layout is theirs. An
app's job is only to *offer* widgets; it never decides where they go.

Four kinds, chosen by what you return:

    ChartWidget   implement `option()` → an ECharts option dict. The house theme,
                  colours, fonts, and dark/light handling are applied for you.
    StatWidget    implement `stat()` → {"value", "label", "delta", "trend"} for a
                  single big number with a sparkline.
    ListWidget    implement `rows()` → a list of {"title", "meta", "status", "url"}.
    TemplateWidget  set `template` and implement `context()` for anything bespoke.

Sizes (Story 48). Declare which of S/M/L/XL your widget supports, smallest
first; the first one you list is its default. **You do not write a variant per
size** — the four base classes above each define what their own kind looks like
at every size (see SIZES below), so a widget you write once renders correctly at
every size it offers, including on the phone. That is deliberate: "renders at
every size it declares" is a promise the platform keeps, not homework for
whoever writes the widget.

A minimal example, in your app's widgets.py:

    from nora_home.dashboard.widgets import ChartWidget

    class WeeklyVolume(ChartWidget):
        title = "Training volume"
        subtitle = "Last 12 weeks"
        sizes = ("L", "XL")
        refresh_seconds = 600

        def option(self, request):
            weeks, volumes = weekly_volume(request.user)
            return {
                "xAxis": {"type": "category", "data": weeks},
                "yAxis": {"type": "value", "name": "kg"},
                "series": [{"type": "bar", "data": volumes}],
            }

Then list it in your AppConfig: `nora_widgets = ["houseapps.workout.widgets.WeeklyVolume"]`.

Keep `option()`/`stat()`/`rows()` fast — a dashboard renders every visible widget
on one page load, and the wall display re-renders forever.
"""

from __future__ import annotations

import logging
from importlib import import_module

from django.template.loader import render_to_string

logger = logging.getLogger(__name__)

# The grid is 12 columns wide. Every size is a whole number of cells on it, so
# any arrangement tiles without ragged gaps — which is the whole claim the size
# system makes, and why arbitrary (w, h) pairs were retired in Story 48.
# Values are (columns, rows), copied from the mockup's own SIZES table.
GRID_COLUMNS = 12
SIZES: dict[str, tuple[int, int]] = {
    "S": (3, 1),
    "M": (6, 1),
    "L": (6, 2),
    "XL": (12, 1),
}
SIZE_NAMES = tuple(SIZES)  # ("S", "M", "L", "XL"), smallest first

# How many rows a list shows at each size it can be a list at. S and M are not
# here on purpose: a 3x1 or 6x1 cell has room for a heading and one line, so a
# list degrades to a summary readout there rather than showing one truncated row
# and pretending that is a list. See ListWidget._body.
LIST_ROWS = {"L": 4, "XL": 6}


def cells(size: str) -> tuple[int, int]:
    """(columns, rows) for a size name, falling back to M for anything unknown
    — a stored layout naming a size this version does not have must render,
    not raise."""
    return SIZES.get(size, SIZES["M"])


class Widget:
    """Base class. You will normally subclass one of the four below instead."""

    title: str = ""
    subtitle: str = ""
    icon: str = ""
    description: str = ""  # shown in the "add a widget" picker
    kind: str = "template"

    # Which of S/M/L/XL this widget offers, smallest first. The first entry is
    # what it gets when someone adds it from the picker.
    sizes: tuple[str, ...] = ("S", "M")
    order: int = 100  # sorts the "add a widget" picker; lower comes first
    refresh_seconds: int = 0
    wall_safe: bool = True  # may this appear on the always-on display?
    template: str = ""

    def __init__(self, app_meta=None):
        self.app = app_meta

    @property
    def key(self) -> str:
        slug = getattr(self.app, "slug", "core")
        return f"{slug}.{type(self).__name__}"

    @property
    def app_title(self) -> str:
        return getattr(self.app, "title", "Nora Home")

    @property
    def default_size(self) -> str:
        """Smallest declared size, which is what the picker places."""
        return self.sizes[0] if self.sizes else "M"

    def resolve_size(self, size: str) -> str:
        """The size to actually render at. A layout may name a size this widget
        no longer offers — a widget can drop a variant, and a stored layout is
        never rewritten behind someone's back — so fall back rather than raise."""
        return size if size in self.sizes else self.default_size

    def is_visible(self, request) -> bool:  # noqa: ARG002
        return True

    def payload(self, request, size: str = "") -> dict:
        """What the browser needs to draw this widget, at one size. Never raises."""
        size = self.resolve_size(size)
        columns, rows = cells(size)
        base = {
            "key": self.key,
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "app": self.app_title,
            "refresh_seconds": self.refresh_seconds,
            "size": size,
            "sizes": list(self.sizes),
            "c": columns,
            "r": rows,
        }
        try:
            base.update(self._body(request, size))
        except Exception:
            logger.exception("Widget %s failed to build its payload", self.key)
            base.update({"kind": "error",
                         "message": "This widget could not load."})
        return base

    def _body(self, request, size: str) -> dict:  # noqa: ARG002
        return {"html": render_to_string(self.template,
                                         {"widget": self, "size": size,
                                          **self.context(request)},
                                         request=request)} if self.template else {}

    def context(self, request) -> dict:  # noqa: ARG002
        return {}

    def as_menu_entry(self) -> dict:
        return {
            "key": self.key,
            "title": self.title,
            "subtitle": self.subtitle,
            "description": self.description,
            "app": self.app_title,
            "kind": self.kind,
            "sizes": list(self.sizes),
            "size": self.default_size,
        }


class ChartWidget(Widget):
    """A chart. Return an ECharts option; the house theme is applied client-side.

    A chart is the one kind that genuinely is the same content at every size —
    it is drawn to fill its tile, so the tile's own cell count is the variant.
    Declaring S is allowed but rarely right: a 3x1 cell is about 150px wide.
    """

    kind = "chart"
    sizes = ("L", "XL")

    def option(self, request) -> dict:  # noqa: ARG002
        raise NotImplementedError("A ChartWidget must implement option().")

    def _body(self, request, size: str) -> dict:  # noqa: ARG002
        return {"option": self.option(request)}


class StatWidget(Widget):
    """One number that matters, with an optional trend line under it."""

    kind = "stat"
    sizes = ("S", "M")

    def stat(self, request) -> dict:  # noqa: ARG002
        """Return {"value", "label", "unit", "delta", "status", "spark"}.

        `status` is ok | warn | alert and colours the tile. `spark` is a plain list
        of numbers for the sparkline; omit it for a bare number.
        """
        raise NotImplementedError("A StatWidget must implement stat().")

    def _body(self, request, size: str) -> dict:
        """S is the bare number and its caption. Everything larger earns the
        sparkline — at 3x1 the number, its unit, a caption and a trend line do
        not all fit, and the line is the first thing that stops being legible
        rather than merely small."""
        stat = dict(self.stat(request))
        if size == "S":
            stat.pop("spark", None)
        return {"stat": stat}


class ListWidget(Widget):
    """A short list — today's items, recent readings, the next few things."""

    kind = "list"
    sizes = ("M", "L")
    empty_message = "Nothing here."
    summary_unit = ""  # e.g. "due", "open" — what the count at S/M counts

    def rows(self, request) -> list[dict]:  # noqa: ARG002
        """Return [{"title", "meta", "status", "url", "action_url"}]."""
        raise NotImplementedError("A ListWidget must implement rows().")

    def summary(self, rows: list[dict]) -> dict:
        """What a list looks like when there is no room to be a list — a count,
        and the one row that matters. Override for a different headline; the
        rows are already fetched, so this costs nothing extra."""
        return {
            "value": len(rows),
            "unit": self.summary_unit,
            "label": rows[0].get("title", "") if rows else self.empty_message,
            "status": rows[0].get("status", "") if rows else "",
        }

    def _body(self, request, size: str) -> dict:
        """A designed state, not a truncation: at S and M this renders as a
        *stat* — the payload's own `kind` changes, and the browser draws a
        readout. One row squeezed into a 6x1 cell reads as a broken list; a
        count with the next item under it reads as an answer."""
        rows = self.rows(request)
        limit = LIST_ROWS.get(size)
        if limit is None:
            return {"kind": "stat", "stat": self.summary(rows)}
        return {"rows": rows[:limit], "empty_message": self.empty_message}


class TemplateWidget(Widget):
    """Anything the other three cannot express. Set `template`, fill `context()`."""

    kind = "template"


def load_widget(dotted: str, app_meta=None) -> Widget | None:
    """Import 'pkg.module.ClassName' and instantiate it. None on any failure."""
    try:
        module_path, class_name = dotted.rsplit(".", 1)
        klass = getattr(import_module(module_path), class_name)
    except Exception:
        logger.exception("Could not load widget %s", dotted)
        return None

    if not isinstance(klass, type) or not issubclass(klass, Widget):
        logger.error("%s is declared as a widget but does not subclass "
                     "nora_home.dashboard.widgets.Widget", dotted)
        return None

    # A size name that is not one of S/M/L/XL would place a tile nowhere at all
    # — `cells()` would fall back to M and the picker would offer a button that
    # does nothing visible. Drop the unknown names, keep the widget, and say so.
    valid = tuple(name for name in klass.sizes if name in SIZES)
    if valid != tuple(klass.sizes):
        logger.warning("Widget %s declares unknown size(s) %r; keeping %r",
                       dotted, [s for s in klass.sizes if s not in SIZES],
                       list(valid) or ["M"])
        klass.sizes = valid or ("M",)
    return klass(app_meta)
