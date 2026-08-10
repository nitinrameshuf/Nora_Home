"""The component library — Story 45.

Two kinds of test here. The first kind proves each `{% nh_* %}` tag renders
what its docstring in `nora_home/ui/templatetags/nh.py` says it does — grounded
against the real widget contract (`nora_home/dashboard/widgets.py`'s
`StatWidget.stat()` / `ListWidget.rows()` shapes), not fixture data invented
for the test.

The second is the cross-layer class-collision audit the story explicitly asks
for. Building the mockup produced four real collisions — `.who` (member name
vs. task assignee), `.cap` (caption vs. fader knob), `.bar` (prototype chrome
vs. vitals track), and a near-miss on `.body` — and every one of them was found
only by looking at a screenshot: none raised a console error, because a later
`@layer` silently winning is not a CSS error. A component library is supposed
to make that class of bug impossible, and the mockup proved it is not
automatic — hence a test, not just a promise.

The audit's first version (built while making the mockup) missed `.bar`
entirely, because it only looked at the first class in a compound selector
like `.vit .bar`. This version reaches the actual subject of a compound
selector rather than stopping at the first token — see _subject_compounds()
for why that is narrower than "every token" and what that excludes on
purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template

pytestmark = pytest.mark.django_db


# ── rendering: each tag against the real widget shapes ───────────────────

def _render(source: str, **context) -> str:
    return Template("{% load nh %}" + source).render(Context(context))


def test_card_renders_its_title_and_body():
    html = _render(
        '{% nh_card title="Due next" subtitle="Todo" %}<p>hello</p>{% endnh_card %}')
    assert "Due next" in html
    assert "Todo" in html
    assert "<p>hello</p>" in html
    assert 'class="card panel"' in html


def test_card_status_tints_without_a_bespoke_class_per_caller():
    html = _render('{% nh_card title="House health" status="crit" %}x{% endnh_card %}')
    assert "card--crit" in html


def test_tile_carries_the_mockups_own_size_table():
    """S:{c:3,r:1}, M:{c:6,r:1}, L:{c:6,r:2}, XL:{c:12,r:1} — copied from the
    mockup's SIZES const, not reinvented."""
    from nora_home.ui.templatetags.nh import TILE_SIZES

    assert TILE_SIZES == {"S": (3, 1), "M": (6, 1), "L": (6, 2), "XL": (12, 1)}

    html = _render('{% nh_tile size="L" %}x{% endnh_tile %}')
    assert "--c:6" in html
    assert "--r:2" in html


def test_sheet_renders_the_phone_compatible_scrim():
    html = _render('{% nh_sheet title="Add a widget" wide=1 %}<button>Done</button>{% endnh_sheet %}')
    assert "scrim" in html
    assert "sheet panel wide" in html
    assert "<button>Done</button>" in html


def test_toolbar_wraps_its_content():
    html = _render('{% nh_toolbar %}<button>A</button><button>B</button>{% endnh_toolbar %}')
    assert html.count("<button>") == 2
    assert 'class="tools"' in html


def test_an_nh_tag_rejects_a_positional_argument():
    """Every nh_card/tile/sheet/toolbar argument is named — CLAUDE.md's own
    convention for these tags, enforced rather than merely documented."""
    from django.template import TemplateSyntaxError

    with pytest.raises(TemplateSyntaxError):
        _render('{% nh_card "Due next" %}x{% endnh_card %}')


def test_stat_matches_statwidgets_own_shape():
    """StatWidget.stat() returns {value, label, unit, delta, status, spark} —
    this is that dict's renderer, so the fixture uses that exact shape."""
    stat = {"value": 52, "label": "Pi temperature", "unit": "C",
            "delta": None, "status": "warn", "spark": [48, 50, 49, 51, 52]}
    html = _render("{% nh_stat value=stat.value label=stat.label unit=stat.unit "
                    "status=stat.status spark=stat.spark %}", stat=stat)
    assert "52" in html
    assert "Pi temperature" in html
    assert 'read warn' in html
    assert "<polyline" in html  # the spark rendered, not skipped


def test_stat_with_no_spark_renders_no_polyline():
    html = _render('{% nh_stat value=4 label="Open now" %}')
    assert "<polyline" not in html


def test_list_matches_listwidgets_own_shape_and_marks_late_rows():
    rows = [
        {"title": "Take the bins out", "meta": "2 days late", "status": "late", "url": "/todo/1/"},
        {"title": "Change the water filter", "meta": "Tomorrow", "status": "", "url": "/todo/2/"},
    ]
    html = _render("{% nh_list rows=rows %}", rows=rows)
    assert "Take the bins out" in html
    assert 'class="d late"' in html
    assert html.count('class="row') == 2


def test_list_falls_back_to_empty_state():
    html = _render('{% nh_list rows=rows empty_message="Nothing due" %}', rows=[])
    assert "Nothing due" in html
    assert 'class="row' not in html


def test_chart_option_survives_a_quote_in_its_own_data():
    """The bug this guards: mark_safe on the JSON would let a `"` inside the
    option dict break out of the HTML attribute it sits in. Django's normal
    auto-escaping is what has to run here — see nh.py's nh_chart docstring."""
    option = {"title": {"text": 'Say "hi"'}}
    html = _render("{% nh_chart option=option key='k' %}", option=option)
    assert 'data-key="k"' in html
    # the attribute is well-formed: exactly one data-option="...", not broken
    # into two attributes by an unescaped quote
    assert len(re.findall(r'data-option="', html)) == 1
    assert "&quot;" in html


def test_ring_matches_the_mockups_own_arc_math():
    """R=42, C=2*pi*R, dashoffset=C*(1-pct/100) — ported, not re-derived."""
    import math

    html = _render("{% nh_ring pct=75 big='75' small='PCT' %}")
    circumference = 2 * math.pi * 42
    offset = circumference * (1 - 75 / 100)
    assert f"{circumference:.3f}" in html
    assert f"{offset:.3f}" in html


def test_ring_clamps_an_out_of_range_percentage():
    html = _render("{% nh_ring pct=140 big='x' small='y' %}")
    import math
    circumference = 2 * math.pi * 42
    assert f"{circumference * (1 - 100 / 100):.3f}" in html  # clamped to 100


def test_key_sets_the_hue_custom_property():
    html = _render("{% nh_key label='Board' hue='#38d6ff' action='nav' value='/todo/' %}")
    assert "--key:#38d6ff" in html
    assert 'data-act="nav"' in html


def test_picker_renders_vertical_by_default_and_horizontal_when_asked():
    items = [{"slug": "home", "title": "Home"}, {"slug": "todo", "title": "Todo"}]
    vertical = _render("{% nh_picker items=items active='todo' %}", items=items)
    horizontal = _render(
        "{% nh_picker items=items active='todo' orientation='horizontal' %}", items=items)

    assert "vsel-list" in vertical and "ph-track" not in vertical
    assert "ph-track" in horizontal and "vsel-list" not in horizontal
    for html in (vertical, horizontal):
        assert html.count('aria-current="true"') == 1
        assert "Home" in html and "Todo" in html


def test_picker_js_never_names_a_method_init():
    """Alpine reserves `init` as an auto-invoked lifecycle hook on any x-data
    object — it calls a method with that exact name itself, with no
    arguments, regardless of what x-init on the element also calls. Naming
    nh-picker.js's own setup method `init` collided with that and threw
    "Cannot read properties of undefined (reading 'dataset')" the moment
    Alpine started, on every page that uses the picker. Console-silent to
    write, console-loud to run — caught by opening the styleguide, not by
    reading the diff."""
    from pathlib import Path

    from django.conf import settings

    js = (Path(settings.BASE_DIR) / "assets" / "js" / "nh-picker.js").read_text(encoding="utf-8")
    assert "\n    init(" not in js, "a component method literally named init() collides with Alpine's own"


def test_picker_icon_is_rendered_unescaped_and_title_is_not():
    """icon is trusted markup (see picker.html); title is always user-visible
    text and must never be — the two must not be treated the same way."""
    items = [{"slug": "a", "title": "<b>Bold</b>", "icon": "<svg><path/></svg>"}]
    html = _render("{% nh_picker items=items %}", items=items)
    assert "<svg><path/></svg>" in html
    assert "<b>Bold</b>" not in html
    assert "&lt;b&gt;Bold&lt;/b&gt;" in html


# ── the cross-layer class-collision audit ─────────────────────────────────

ASSETS_CSS = Path(settings.BASE_DIR) / "assets" / "css"

# Collisions already known and accepted, because the file on one side of them
# is scheduled for deletion rather than fixed — CLAUDE.md §4, "the front end
# is rewritten from the mockup, not migrated": assets/css/{dashboard,displays,
# nh-bot,nh-scene,nora-home,todo}.css all go when the real templates are
# rewired onto this component library. Until then, the same class name
# legitimately means two different things in the old system and the new one.
# Same shape as tests/test_house_apps.py's KNOWN_MODEL_IMPORT_DEBT: named,
# dated, and meant to shrink to nothing rather than grow.
KNOWN_OLD_VS_NEW_COLLISIONS = {
    # nh-scene.css (kept until Story 46) adds glass-pane background/blur/
    # text-legibility to these — non-conflicting properties layered on top of
    # what components.css/shell.css already draw, same relationship as .card.
    "card", "empty", "dash__empty",
    "kiosk-header", "kiosk-tile", "kiosk-controls", "kiosk-tile__hint",
}

RULE = re.compile(r"([^{}]+)\{([^{}]*)\}")
CLASS_TOKEN = re.compile(r"\.(-?[a-zA-Z_][\w-]*)")

# See _subject_compounds() below for what counts as a comparable selector
# and why: comparing every class token naively (the story's `warn` field, read
# literally) flags this codebase's own everyday CSS — hover states, this
# codebase's [data-surface]/[data-app] override convention, structural
# nesting — as "colliding" with itself. Only bare, unscoped selectors are
# compared, which is what the mockup's actual .who/.cap/.bar bugs were.
COMBINATOR = re.compile(r"\s*[>+~]\s*")


def _strip_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


_LAYER_OPEN = re.compile(r"@layer\s+([\w, -]+?)\s*\{")


def _layer_of(css: str, rule_start: int) -> str:
    """Which `@layer NAME { ... }` (if any) contains the rule starting at
    `rule_start`. A plain `@layer a, b;` (no braces — just an order
    declaration) is not a scope and is ignored.

    Each layer is popped when brace depth returns to the exact depth it was
    pushed at, not merely "some depth less than before" — the difference
    matters because every ordinary rule inside a layer (`.foo { ... }`) opens
    and closes its own brace pair without ending the layer."""
    depth = 0
    stack: list[tuple[str, int]] = []  # (layer_name, depth_when_pushed)
    i = 0
    while i < rule_start:
        match = _LAYER_OPEN.match(css, i)
        if match:
            depth += 1
            stack.append((match.group(1).strip(), depth))
            i = match.end()
            continue
        if css[i] == "{":
            depth += 1
        elif css[i] == "}":
            if stack and stack[-1][1] == depth:
                stack.pop()
            depth -= 1
        i += 1
    return stack[-1][0] if stack else "(unlayered)"


def _subject_compounds(selector: str) -> list[str]:
    """Each comma-separated selector, kept ONLY when the *entire* selector is
    one bare compound of chained classes — no ancestor, no tag, no pseudo-
    class or -element, no attribute selector. e.g. ".read.crit" -> "read.crit",
    but ".vit .bar", ".hkey:hover" and 'html[data-surface="phone"] .card' are
    all dropped.

    This is deliberately narrower than "every class token" (the story's
    literal `warn` text) — a first, broader version of this audit compared
    every rightmost subject regardless of ancestor, and it flagged this
    codebase's own everyday CSS as "colliding": `.btn` vs. `.btn:hover` (a
    state variant), `.card` vs. `html[data-app] .card` (this codebase's own,
    deliberate, extensively-documented `[data-surface]`/`[data-app]` override
    mechanism — see CLAUDE.md §4), `.card` vs. `.nh-tile > .card` (a
    structural refinement, not a redefinition). None of those are the bug
    the mockup actually hit: `.who`, `.cap`, `.bar` and `.body` were each a
    *bare* class, defined as a complete, unscoped selector, in two unrelated
    `@layer` blocks with nothing in common but the name. Comparing only bare
    selectors reproduces exactly that failure mode and stops there, so a
    deliberate override does not have to out-shout a genuine accident."""
    out = []
    for part in selector.split(","):
        part = COMBINATOR.sub(" ", part.strip())
        if not part or " " in part:
            continue  # has an ancestor — a scoped override, not a bare redefinition
        classes = CLASS_TOKEN.findall(part)
        if classes and CLASS_TOKEN.sub("", part) == "":
            out.append(".".join(classes))
    return out


def _class_rules(path: Path) -> list[tuple[str, str, str, str]]:
    """[(subject_compound, layer, normalized_body, file)] — one entry per
    selector's actual subject, not every class token in the whole selector.
    See the COMBINATOR comment above for why."""
    css = _strip_comments(path.read_text(encoding="utf-8"))
    out = []
    for match in RULE.finditer(css):
        selector, body = match.group(1), match.group(2)
        if selector.lstrip().startswith("@"):
            continue  # @media/@keyframes conditions, not a real selector
        subjects = _subject_compounds(selector)
        if not subjects:
            continue
        layer = _layer_of(css, match.start())
        normalized_body = re.sub(r"\s+", " ", body).strip()
        for name in subjects:
            out.append((name, layer, normalized_body, path.name))
    return out


def test_no_class_means_two_different_things_across_the_new_component_files():
    """Scoped to tokens.css + components.css only — the two files Story 45
    actually wrote. A name reused for something unrelated *within the new
    system* is the mockup's bug recurring; a name shared with the old system,
    scheduled for deletion, is not — see KNOWN_OLD_VS_NEW_COLLISIONS."""
    all_rules: list[tuple[str, str, str, str]] = []
    for name in ("tokens.css", "components.css"):
        path = ASSETS_CSS / name
        assert path.exists(), f"{name} is gone — update this test's file list"
        all_rules.extend(_class_rules(path))

    by_class: dict[str, set[str]] = {}
    for class_name, _layer, body, _file in all_rules:
        by_class.setdefault(class_name, set()).add(body)

    genuine = {name: bodies for name, bodies in by_class.items() if len(bodies) > 1}
    assert not genuine, (
        f"the same class means different things across tokens.css/components.css: "
        f"{sorted(genuine)} — see the mockup's .who/.cap/.bar collisions for what "
        f"this looks like when it reaches a screenshot instead of a test")


def test_old_vs_new_collisions_are_the_known_ones_and_no_more():
    """Not a failure by itself — see KNOWN_OLD_VS_NEW_COLLISIONS. This exists
    so a *new*, unplanned collision between a file being kept and the old
    system announces itself here rather than on a screen no one is looking
    at, and so the allowlist above is honest about its own size."""
    old_files = ["dashboard.css", "displays.css", "nh-bot.css", "nh-scene.css",
                 "nora-home.css", "todo.css"]
    new_files = ["tokens.css", "components.css"]

    old_classes: dict[str, set[str]] = {}
    for name in old_files:
        path = ASSETS_CSS / name
        if not path.exists():
            continue  # Phase B deleted it — nothing left to collide with
        for class_name, _layer, body, _file in _class_rules(path):
            old_classes.setdefault(class_name, set()).add(body)

    new_classes: set[str] = set()
    for name in new_files:
        for class_name, _layer, _body, _file in _class_rules(ASSETS_CSS / name):
            new_classes.add(class_name)

    found = new_classes & set(old_classes)
    unexpected = found - KNOWN_OLD_VS_NEW_COLLISIONS
    assert not unexpected, (
        f"new collision(s) with the old system not yet in "
        f"KNOWN_OLD_VS_NEW_COLLISIONS: {sorted(unexpected)}")

    stale = KNOWN_OLD_VS_NEW_COLLISIONS - found
    assert not stale, (
        f"KNOWN_OLD_VS_NEW_COLLISIONS lists names that no longer collide — "
        f"shrink the allowlist: {sorted(stale)}")


def test_every_tile_grid_gets_the_sizing_rule():
    """`.nh-tile`'s --c/--r custom properties (set inline, per tile) only take
    effect where a `grid-column: span var(--c)` rule actually matches — and
    that rule was scoped to `.bento > .nh-tile` only. Reporting's own grid
    (`.report-grid`) used the same --c/--r-bearing tiles but matched nothing,
    so every report card rendered as a single default-width column instead of
    the 6- or 12-wide span it asked for — text wrapped to a few characters
    per line. Found by opening the page; every template and Python test
    stayed green, because the tiles and their --c/--r were both present and
    correct, and only the CSS connecting them to a grid track was missing."""
    css = (ASSETS_CSS / "components.css").read_text(encoding="utf-8")
    for grid_class in (".bento", ".report-grid"):
        assert f"{grid_class} > .nh-tile" in css, (
            f"{grid_class} has no `> .nh-tile` sizing rule — its tiles' "
            f"--c/--r will be set but never read")
