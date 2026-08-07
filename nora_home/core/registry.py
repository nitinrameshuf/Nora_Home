"""
The app registry — how Nora Home stays a platform instead of a monolith.

A house app declares itself by subclassing NoraAppConfig in its apps.py:

    from nora_home.core.registry import NoraAppConfig, Category

    class WorkoutConfig(NoraAppConfig):
        name = "houseapps.workout"
        nora_slug = "workout"
        nora_title = "Workout"
        nora_icon = "dumbbell"
        nora_category = Category.FAMILY
        nora_description = "Lifts, runs, and how the week actually went."
        nora_nav = True
        nora_dashboard_cards = ["houseapps.workout.cards.WeekVolumeCard"]

That is the entire contract. From it the platform derives:

  * the URL mount at /app/workout/ (if the app ships a urls.py),
  * a nav entry grouped under its category,
  * dashboard cards on the home screen and the wall display,
  * a namespace for notifications, telemetry series, and object-storage keys,
  * an entry in the MCP tool listing so agents can see the app exists.

Nothing here imports app code at settings time; discovery runs after Django's app
registry is populated, so a broken house app degrades to a warning rather than
taking the whole house down.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from importlib import import_module

from django.apps import AppConfig, apps
from django.urls import include, path

logger = logging.getLogger(__name__)


class Category:
    """Top-level groupings on the dashboard. Extend deliberately — the wall display
    lays out one column per category."""

    SELF = "self"
    AMBITION = "ambition"
    FAMILY = "family"
    ROBOT = "robot"
    HOUSE = "house"
    INTEGRATIONS = "integrations"
    SYSTEM = "system"

    LABELS = {
        SELF: "Self Improvement",
        AMBITION: "Ambition",
        FAMILY: "Family",
        ROBOT: "Nora Robot",
        HOUSE: "House",
        INTEGRATIONS: "Integrations",
        SYSTEM: "System",
    }
    ORDER = [SELF, AMBITION, FAMILY, ROBOT, HOUSE, INTEGRATIONS, SYSTEM]

    @classmethod
    def label(cls, key: str) -> str:
        return cls.LABELS.get(key, key.title())


class NoraAppConfig(AppConfig):
    """Base AppConfig for every app that wants to appear inside Nora Home."""

    # Django finds an app's config by inspecting every AppConfig subclass in its
    # apps.py. Because that file also imports *this* class, there are always two
    # candidates — and with no tie-breaker Django quietly falls back to a plain
    # AppConfig, which makes the whole registry come back empty. Excluding the base
    # and marking real subclasses as the default is what keeps discovery working
    # without every house app having to remember `default = True`.
    default = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.default = True

    # Identity
    nora_slug: str = ""
    nora_title: str = ""
    nora_description: str = ""
    nora_icon: str = "sparkle"
    nora_category: str = Category.HOUSE
    nora_color: str = ""  # optional accent, e.g. "#7dd3fc"

    # Levels — the dependency rule (docs/Main_App/subsystems/todo.md §1).
    #   1  the base platform (nora_home/*) — nothing may depend downward on 3
    #   2  apps the base leans on (e.g. Todo) — deliberately uninstallable,
    #      and the base degrades without one
    #   3  family apps (houseapps/*), the default — uninstall freely
    # Platform apps must set this explicitly; nothing here infers it from the
    # module path, because a Level 2 app also lives outside houseapps/.
    nora_level: int = 3

    # Placement
    nora_nav: bool = True
    nora_order: int = 100
    nora_url_prefix: str = ""  # defaults to <slug>/ — apps live at the URL root
    nora_dashboard_cards: list[str] = []
    nora_widgets: list[str] = []  # visualizations selectable on the home dashboard
    # Buttons the 10.1" kiosk shows once someone has switched the wall to this
    # app — e.g. [{"title": "Log a set", "path": "/workout/log/"}]. Optional:
    # an app with none just gets the default single tile that switches to it.
    nora_kiosk_controls: list[dict] = []
    # The app's own pages, shown in the sidebar while someone is inside it —
    # e.g. [{"title": "Calendar", "path": "/todo/calendar/"}]. Same shape as
    # nora_kiosk_controls but a different job, and deliberately not the same
    # list: the kiosk gets a handful of big touch targets for driving the wall,
    # a sidebar can afford every section an app has.
    #
    # Without this an app's sub-pages are reachable only by typing a URL. The
    # sidebar is the platform's navigation, and until 2026-08-07 it showed the
    # house's own pages and nothing else no matter where you were.
    nora_sections: list[dict] = []

    # Capability flags the platform uses to decide what to wire up
    nora_provides_mcp_tools: bool = False
    nora_owns_telemetry_series: list[str] = []
    nora_minimum_role: str = "member"  # member | adult | admin

    # Set False to keep an app installed but hidden (half-built, or seasonal).
    nora_enabled: bool = True

    # Most NoraAppConfigs mount a urls.py somewhere real. A few platform ones
    # (ui, datastores) exist purely to hold registry metadata — widget
    # ownership, telemetry provenance — and have no urls.py and no page of
    # their own at all; their url_prefix would otherwise be pure fiction on
    # the Apps directory (either 404ing or silently landing on some other
    # app's unrelated page). Set False there so the directory only ever
    # links to something that's actually reachable.
    nora_has_page: bool = True

    @property
    def nora_home_metadata(self) -> "AppMetadata":
        return AppMetadata(
            slug=self.nora_slug or self.label,
            title=self.nora_title or self.verbose_name or self.label.title(),
            description=self.nora_description,
            icon=self.nora_icon,
            category=self.nora_category,
            color=self.nora_color,
            module=self.name,
            level=self.nora_level,
            nav=self.nora_nav,
            has_page=self.nora_has_page,
            order=self.nora_order,
            url_prefix=self.nora_url_prefix or f"{self.nora_slug or self.label}/",
            dashboard_cards=list(self.nora_dashboard_cards),
            widgets=list(self.nora_widgets),
            kiosk_controls=list(self.nora_kiosk_controls),
            sections=list(self.nora_sections),
            provides_mcp_tools=self.nora_provides_mcp_tools,
            telemetry_series=list(self.nora_owns_telemetry_series),
            minimum_role=self.nora_minimum_role,
            enabled=self.nora_enabled,
            is_platform=self.name.startswith("nora_home."),
        )


@dataclass(frozen=True)
class AppMetadata:
    slug: str
    title: str
    description: str
    icon: str
    category: str
    color: str
    module: str
    nav: bool
    has_page: bool
    order: int
    url_prefix: str
    level: int = 3
    dashboard_cards: list[str] = field(default_factory=list)
    widgets: list[str] = field(default_factory=list)
    kiosk_controls: list[dict] = field(default_factory=list)
    sections: list[dict] = field(default_factory=list)
    provides_mcp_tools: bool = False
    telemetry_series: list[str] = field(default_factory=list)
    minimum_role: str = "member"
    enabled: bool = True
    is_platform: bool = False

    @property
    def category_label(self) -> str:
        return Category.label(self.category)

    @property
    def url(self) -> str:
        return "/" + self.url_prefix.lstrip("/")


def registered_apps(include_disabled: bool = False) -> list[AppMetadata]:
    """Every NoraAppConfig currently installed, sorted for display."""
    found: list[AppMetadata] = []
    for config in apps.get_app_configs():
        if not isinstance(config, NoraAppConfig):
            continue
        meta = config.nora_home_metadata
        if meta.enabled or include_disabled:
            found.append(meta)
    found.sort(key=lambda m: (Category.ORDER.index(m.category)
                              if m.category in Category.ORDER else 99,
                              m.order, m.title))
    return found


def house_apps(include_disabled: bool = False) -> list[AppMetadata]:
    """Apps the family wrote, as opposed to platform apps."""
    return [m for m in registered_apps(include_disabled=include_disabled) if not m.is_platform]


def navigation(role: str = "member") -> list[dict]:
    """Nav tree grouped by category, filtered to what this role may see."""
    rank = {"member": 0, "adult": 1, "admin": 2}
    viewer = rank.get(role, 0)
    groups: dict[str, list[AppMetadata]] = {}
    for meta in registered_apps():
        if not meta.nav or viewer < rank.get(meta.minimum_role, 0):
            continue
        groups.setdefault(meta.category, []).append(meta)
    return [
        {"key": key, "label": Category.label(key), "apps": groups[key]}
        for key in Category.ORDER
        if key in groups
    ]


def app_for_path(path: str) -> "AppMetadata | None":
    """Which app this URL is *inside*, or `None` on the platform's own pages.

    This is the distinction the sidebar and the pane opacity both key off, so
    what counts as "an app" matters:

    **Anything mounted under `/home/` is the base platform, not an app.** The
    house's own pages live there — the dashboard, Alerts, Measurements, the
    House log, Settings — and several are separate Django apps internally
    (`notifications` at `/home/alerts/`, `telemetry` at `/home/measurements/`)
    purely for code organisation. Nobody "went into" an app by opening Alerts,
    and the living background is meant to be the point on those pages.

    An app is something with its own top-level slug: Todo at `/todo/`, and every
    house app under `houseapps/`. Level is deliberately *not* the test — Todo is
    Level 2 and `is_platform`, but it is an app in every way a person cares
    about.

    Longest prefix wins, so a future `/todo/reports/` app would beat `/todo/`.
    """
    path = "/" + (path or "").lstrip("/")
    candidates = [
        meta for meta in registered_apps()
        if meta.has_page
        and not meta.url_prefix.strip("/").startswith("home")
        and path.startswith("/" + meta.url_prefix.strip("/") + "/")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda m: len(m.url_prefix))


# Prefixes the platform owns. A house app may not claim one of these, because its
# URLs sit at the root alongside them (/workout, /family, …) rather than under a
# shared /app/ prefix.
RESERVED_SLUGS = {
    "home", "admin", "api", "mcp", "static", "media", "ws", "accounts", "app",
    "health", "login", "logout", "favicon.ico", "robots.txt", "manifest.webmanifest",
    "sw.js",
}


def house_app_urlpatterns() -> list:
    """URL entries for every registered app that ships a urls.py.

    House apps mount at the URL root — /workout/, /family/, /maintenance/ — so each
    one reads like its own site. A broken or colliding app is skipped with a logged
    error rather than taken as fatal: one bad app must never stop the wall display
    from booting.
    """
    patterns = []
    for meta in registered_apps():
        if meta.is_platform:
            continue  # platform routes are mounted explicitly in config/urls.py

        first_segment = meta.url_prefix.strip("/").split("/")[0]
        if first_segment in RESERVED_SLUGS:
            logger.error(
                "House app %s wants /%s/, which the platform reserves. Change its "
                "nora_slug or set nora_url_prefix.", meta.module, first_segment)
            continue

        module_path = f"{meta.module}.urls"
        try:
            import_module(module_path)
        except ModuleNotFoundError:
            continue
        except Exception:
            logger.exception("House app %s has a broken urls.py; skipping mount", meta.slug)
            continue

        patterns.append(path(meta.url_prefix, include((module_path, meta.slug),
                                                      namespace=meta.slug)))
        logger.debug("Mounted house app %s at /%s", meta.slug, meta.url_prefix)
    return patterns


def dashboard_cards(role: str = "member") -> list:
    """Instantiate every declared dashboard card. See nora_home.core.cards.Card."""
    from nora_home.core.cards import load_card

    rank = {"member": 0, "adult": 1, "admin": 2}
    viewer = rank.get(role, 0)
    cards = []
    for meta in registered_apps():
        if viewer < rank.get(meta.minimum_role, 0):
            continue
        for dotted in meta.dashboard_cards:
            card = load_card(dotted, meta)
            if card is not None:
                cards.append(card)
    cards.sort(key=lambda c: (c.order, c.title))
    return cards


def all_widgets(role: str = "member") -> list:
    """Every visualization apps offer for the home dashboard.

    This is the menu someone picks from when arranging their own home screen; what
    they actually chose lives in nora_home.dashboard.models.DashboardLayout.
    """
    from nora_home.dashboard.widgets import load_widget

    rank = {"member": 0, "adult": 1, "admin": 2}
    viewer = rank.get(role, 0)
    widgets = []
    for meta in registered_apps():
        if viewer < rank.get(meta.minimum_role, 0):
            continue
        for dotted in meta.widgets:
            widget = load_widget(dotted, meta)
            if widget is not None:
                widgets.append(widget)
    widgets.sort(key=lambda w: (w.order, w.title))
    return widgets


def get_widget(key: str, role: str = "member"):
    """Look one widget up by its registry key (`<app-slug>.<ClassName>`)."""
    for widget in all_widgets(role):
        if widget.key == key:
            return widget
    return None


def scope_members(request) -> list:
    """Who a widget's data should be filtered to.

    Normally just the person looking at the screen. In "Everyone" switcher scope,
    every active house member — a widget that filters on this instead of
    `request.user` directly gets the combined view for free.
    """
    if request.session.get("nh_view_scope") == "all":
        from nora_home.accounts.models import HouseMember
        return list(HouseMember.objects.filter(is_active=True))
    return [request.user]
