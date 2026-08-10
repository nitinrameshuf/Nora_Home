"""
The house's icon set — one name to one piece of SVG path markup.

Every app already declares `nora_icon` on its NoraAppConfig (a *name*, like
"bell"), and until Story 50 nothing anywhere turned that name into a drawing:
base.html hand-writes its own brand mark, and the Picker component's own
docstring says it "has no icon-name lookup of its own". The kiosk's app
scroller is the first surface that genuinely needs one — a column of unlabelled
text rows is not the control desk the mockup designed — so the lookup lives
here, once, rather than in that one template.

Paths are copied from docs/Main_App/ui-overhaul-mockup.html's own `I` map (the
approved reference, CLAUDE.md §4) rather than redrawn. Two entries are not from
it and are marked: the mockup's REGISTRY only ever held Home and Todo, so it
never needed an icon for Integrations.

Rendered inside a shared <svg> wrapper by `{% nh_icon %}`, so every icon in the
house gets the same stroke weight and line joins whatever draws it.
"""

from __future__ import annotations

from django.utils.safestring import mark_safe

# name -> the *inside* of a 24x24 <svg>, stroked not filled.
_PATHS = {
    # ── from the mockup's own I map ──
    "home": '<path d="M3 11l9-8 9 8"/><path d="M5 10v10h14V10"/>',
    "task": ('<path d="M9 11l2 2 4-4"/><rect x="3" y="4" width="18" height="17" rx="3"/>'
             '<path d="M8 2v4M16 2v4"/>'),
    "bell": ('<path d="M18 8A6 6 0 106 8c0 7-3 9-3 9h18s-3-2-3-9"/>'
             '<path d="M13.7 21a2 2 0 01-3.4 0"/>'),
    "chart": '<path d="M3 17l5-6 4 4 5-8 4 5"/>',
    "grid": ('<rect x="3" y="3" width="7" height="7" rx="1.5"/>'
             '<rect x="14" y="3" width="7" height="7" rx="1.5"/>'
             '<rect x="3" y="14" width="7" height="7" rx="1.5"/>'
             '<rect x="14" y="14" width="7" height="7" rx="1.5"/>'),
    "log": '<path d="M4 5h16M4 12h16M4 19h10"/>',
    "gear": ('<circle cx="12" cy="12" r="3.2"/>'
             '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9L7 7M17 17l2.1 2.1'
             'M19.1 4.9L17 7M7 17l-2.1 2.1"/>'),
    "wrench": '<path d="M14 7l3 3M3 21l3-1 11-11-2-2L4 18z"/>',
    "menu": '<path d="M4 6h16M4 12h16M4 18h16"/>',
    "screen": '<rect x="2" y="4" width="20" height="13" rx="2"/><path d="M8 21h8M12 17v4"/>',

    # ── not in the mockup; it only ever registered Home and Todo ──
    # Todo declares nora_icon="check"; the mockup drew that same app with its
    # "task" glyph, so this is an alias rather than a second drawing.
    "check": ('<path d="M9 11l2 2 4-4"/><rect x="3" y="4" width="18" height="17" rx="3"/>'
              '<path d="M8 2v4M16 2v4"/>'),
    # Integrations. The one genuinely new glyph here — a chain link.
    "link": ('<path d="M10 13a5 5 0 007.5.5l3-3a5 5 0 00-7-7l-1.7 1.7"/>'
             '<path d="M14 11a5 5 0 00-7.5-.5l-3 3a5 5 0 007 7l1.7-1.7"/>'),
}

_WRAPPER = ('<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" '
            'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" '
            'aria-hidden="true">{paths}</svg>')


def icon(name: str) -> str:
    """Trusted SVG markup for `name`, or "" when there is no such icon.

    Empty rather than a placeholder glyph on purpose: every caller already
    guards on falsiness (`{% if item.icon %}` in picker.html), and a house app
    that declares an icon name this house has never heard of should render as
    a plain labelled row, not as a question mark nobody can interpret.
    """
    paths = _PATHS.get(name or "")
    return mark_safe(_WRAPPER.format(paths=paths)) if paths else ""


def names() -> list[str]:
    """Every icon name this house can draw. Used by the test that checks no
    registered app declares one that would silently render as nothing."""
    return sorted(_PATHS)
