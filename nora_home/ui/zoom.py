"""
How big the two fixed screens render, set from Settings rather than over SSH.

The 24" is read from about three metres and the 10.1" from arm's length, and a
browser cannot work either of those out for itself — a CSS pixel is already a
*reference pixel* (the visual angle of one pixel on a 96dpi screen at arm's
length), and `devicePixelRatio` normalises for physical size, but nothing
measures **distance**. So it has to be told, and the person standing in front of
the screen is the only one who can judge it.

## Why this is CSS `zoom` and not `--force-device-scale-factor`

The Chromium flag was tried first and is arguably the more native mechanism —
it is what TV and signage platforms use. It was abandoned for one practical
reason: a launch flag can only be changed by regenerating the launch script and
restarting the browser, which means an SSH session. A number a family member is
expected to tune belongs somewhere they can reach.

CSS `zoom` was measured against the flag on the Pi's own Chromium before being
chosen, because "zoom scales everything" needed to be a fact and not a hope:

    a 100px box with 10px borders   plain 120px  ->  zoomed 1.25  150px
    html { zoom: 1.25 } on 1920     documentElement.clientWidth   1536

Both match `--force-device-scale-factor=1.25` exactly. **This is the property
that matters**, and it is what scaling the root `font-size` never had: borders,
shadows and corner radii scale with the text instead of staying
1-device-pixel hairlines while everything around them grows. That mismatch is
what reads as "zoomed in", and it is why the font-size approach was rejected
twice before this.

**This is a distance dial, not a type scale.** Since Story 44, `assets/css/tokens.css`
gives each surface its own `--s0`..`--s4` ramp — the wall's base size is already
larger than the kiosk's, because it is read from three metres rather than arm's
length. `zoom` sits on top of that ramp for whatever the ramp does not get
exactly right in one house, the same way a person might still nudge browser zoom
on a laptop. It no longer does the whole job by itself.

**The one measured difference: media queries still evaluate against the
unzoomed viewport.** With `html { zoom: 1.25 }` on a 1920 screen, layout happens
in 1536 but `(min-width: 1900px)` still matches. The house's breakpoints are at
860px and 620px, so nothing changes on the wall at any sane zoom. It *can* bite
the 10.1" kiosk: at 1024 physical, a zoom above ~1.2 puts the layout viewport
under 860 while media queries still report 1024, so the narrow-screen rules
would not fire when the layout has become narrow. `MAX_ZOOM` is deliberately
low enough on the kiosk to keep it clear of that.
"""

from __future__ import annotations

SETTING_KEY = "displays.zoom"

# The wall's default is the value that measured right on the real 24" at three
# metres (1.25); the kiosk's is 1 because a touchscreen at arm's length is
# exactly the case every browser default already assumes.
DEFAULTS = {"wall": 1.25, "kiosk": 1.0}

# Below 0.8 the house is unreadable; above these it stops being a layout and
# becomes a magnifier. The kiosk's ceiling is lower on purpose — see the module
# docstring on media queries and the 860px breakpoint.
MIN_ZOOM = 0.8
MAX_ZOOM = {"wall": 2.0, "kiosk": 1.2}

# Only the two fixed-purpose screens. Phones and laptops are held at arm's
# length, which is what the browser already assumes, so there is nothing to
# correct and nothing worth letting anyone break.
ADJUSTABLE = ("wall", "kiosk")


def clamp(surface: str, value) -> float:
    """A usable zoom for `surface`, whatever it is handed.

    Never raises. This is read on the way to rendering the wall, and a bad
    stored value must not be able to take the always-on screen down — it falls
    back to the default for that surface instead.
    """
    try:
        number = round(float(value), 2)
    except (TypeError, ValueError):
        return DEFAULTS.get(surface, 1.0)
    ceiling = MAX_ZOOM.get(surface, 2.0)
    return min(max(number, MIN_ZOOM), ceiling)


def stored() -> dict:
    """Both screens' zoom levels, defaults filled in for anything unset."""
    from nora_home.core.settings_store import get_setting

    saved = get_setting(SETTING_KEY, default={}) or {}
    if not isinstance(saved, dict):  # a hand-edited row, or an older shape
        saved = {}
    return {surface: clamp(surface, saved.get(surface, DEFAULTS[surface]))
            for surface in ADJUSTABLE}


def save(values: dict, *, actor=None) -> dict:
    """Persist both levels and return what was actually stored after clamping."""
    from nora_home.core.audit import record
    from nora_home.core.settings_store import set_setting

    cleaned = {surface: clamp(surface, values.get(surface, DEFAULTS[surface]))
               for surface in ADJUSTABLE}
    set_setting(SETTING_KEY, cleaned, app_slug="displays",
                description="How large the wall and kiosk render, as a zoom factor.")
    # The new values, not just the fact of a change: "why did the wall go
    # enormous on Tuesday" is only answerable if the log says what it went to.
    record("displays", "zoom.changed", actor=actor,
           subject="Screen zoom", **{f"{k}_zoom": v for k, v in cleaned.items()})
    return cleaned


def for_surface(surface: str) -> float | None:
    """The zoom to apply for this request, or None when there is nothing to do.

    `None` rather than `1.0` on purpose: the template uses it to decide whether
    to emit a `style` attribute at all, so a laptop's markup is untouched by a
    feature that does not concern it.
    """
    if surface not in ADJUSTABLE:
        return None
    try:
        value = stored()[surface]
    except Exception:  # noqa: BLE001 — a settings lookup must not break a screen
        value = DEFAULTS[surface]
    return value if value != 1.0 else None
