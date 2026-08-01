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

A minimal example, in your app's widgets.py:

    from nora_home.dashboard.widgets import ChartWidget

    class WeeklyVolume(ChartWidget):
        title = "Training volume"
        subtitle = "Last 12 weeks"
        default_size = (6, 4)
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

# The grid is 12 columns wide. Sizes are (columns, rows); a row is ~80px.
GRID_COLUMNS = 12
MAX_ROWS = 12


class Widget:
    """Base class. You will normally subclass one of the four below instead."""

    title: str = ""
    subtitle: str = ""
    icon: str = ""
    description: str = ""  # shown in the "add a widget" picker
    kind: str = "template"

    default_size: tuple[int, int] = (4, 3)
    min_size: tuple[int, int] = (2, 2)
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

    def is_visible(self, request) -> bool:  # noqa: ARG002
        return True

    def payload(self, request) -> dict:
        """What the browser needs to draw this widget. Never raises."""
        base = {
            "key": self.key,
            "kind": self.kind,
            "title": self.title,
            "subtitle": self.subtitle,
            "app": self.app_title,
            "refresh_seconds": self.refresh_seconds,
        }
        try:
            base.update(self._body(request))
        except Exception:
            logger.exception("Widget %s failed to build its payload", self.key)
            base.update({"kind": "error",
                         "message": "This widget could not load."})
        return base

    def _body(self, request) -> dict:
        return {"html": render_to_string(self.template,
                                         {"widget": self, **self.context(request)},
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
            "w": self.default_size[0],
            "h": self.default_size[1],
        }


class ChartWidget(Widget):
    """A chart. Return an ECharts option; the house theme is applied client-side."""

    kind = "chart"
    default_size = (6, 4)

    def option(self, request) -> dict:  # noqa: ARG002
        raise NotImplementedError("A ChartWidget must implement option().")

    def _body(self, request) -> dict:
        return {"option": self.option(request)}


class StatWidget(Widget):
    """One number that matters, with an optional trend line under it."""

    kind = "stat"
    default_size = (3, 2)

    def stat(self, request) -> dict:  # noqa: ARG002
        """Return {"value", "label", "unit", "delta", "status", "spark"}.

        `status` is ok | warn | alert and colours the tile. `spark` is a plain list
        of numbers for the sparkline; omit it for a bare number.
        """
        raise NotImplementedError("A StatWidget must implement stat().")

    def _body(self, request) -> dict:
        return {"stat": self.stat(request)}


class ListWidget(Widget):
    """A short list — today's items, recent readings, the next few things."""

    kind = "list"
    default_size = (4, 4)
    empty_message = "Nothing here."

    def rows(self, request) -> list[dict]:  # noqa: ARG002
        """Return [{"title", "meta", "status", "url", "action_url"}]."""
        raise NotImplementedError("A ListWidget must implement rows().")

    def _body(self, request) -> dict:
        return {"rows": self.rows(request), "empty_message": self.empty_message}


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

    width, height = klass.default_size
    if not (1 <= width <= GRID_COLUMNS and 1 <= height <= MAX_ROWS):
        logger.warning("Widget %s has an out-of-range default_size %r; clamping",
                       dotted, klass.default_size)
        klass.default_size = (min(max(width, 1), GRID_COLUMNS),
                              min(max(height, 1), MAX_ROWS))
    return klass(app_meta)
