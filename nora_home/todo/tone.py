"""
Tone presets (docs/Main_App/subsystems/todo.md §10, "Tone").

**The gentler defaults are defaults, not rules.** A preset sets everything at
once; individual overrides sit underneath it. Nothing is withheld from anyone —
someone who wants a streak that resets to zero on a miss can have one, and
someone who never wants to see a number in red can have that instead.

This module holds *what each preset means*, and nothing else. It does no
counting; `nora_home.todo.analytics` does that and stays entirely
tone-agnostic, because a statistic must not change depending on how someone
prefers to be spoken to. Tone decides **presentation** — which of the same
numbers are shown, in what words, in what colour.
"""

from __future__ import annotations

from nora_home.todo.models import Tone

# Every setting a preset controls, with the values it may take. Adding a row
# here is the only change needed to add a setting: the resolver, the settings
# form and the template all read this.
SETTINGS = {
    # "ratio" — 19 of the last 30. "classic" — consecutive, resets on a miss.
    "streaks": ("ratio", "classic"),
    # Which counts may render in the alert colour.
    "counts_in_red": ("never", "overdue", "everything"),
    # A leaderboard across the household, or each person's own numbers only.
    "compare_members": (False, True),
    # "gentle" says "Moved 11 times"; "plain" says "Overdue 11 days".
    "wording": ("gentle", "plain"),
    # Whether pattern observations escape the Reporting page onto the home screen.
    "observations_on_home": (False, True),
    # How many upcoming items the wall, kiosk and widgets show. None = all.
    "upcoming_count": (3, 5, None),
}

PRESETS = {
    Tone.CALM: {
        "streaks": "ratio",
        "counts_in_red": "never",
        "compare_members": False,
        "wording": "gentle",
        "observations_on_home": False,
        "upcoming_count": 3,
    },
    Tone.STANDARD: {
        "streaks": "ratio",
        "counts_in_red": "overdue",
        "compare_members": False,
        "wording": "plain",
        "observations_on_home": False,
        "upcoming_count": 5,
    },
    Tone.COMPETITIVE: {
        "streaks": "classic",
        "counts_in_red": "everything",
        "compare_members": True,
        "wording": "plain",
        "observations_on_home": True,
        "upcoming_count": None,
    },
}


def resolve(member) -> dict:
    """The settings actually in force for this person: their preset, with any
    individual overrides laid on top.

    A member with no `TodoPreference` row at all gets Standard — the default
    has to work before anyone has visited the settings page, since the wall
    and the kiosk render for people who may never open it.
    """
    from nora_home.todo.models import TodoPreference

    preference = TodoPreference.objects.filter(member=member).first() if member else None
    preset = PRESETS.get(getattr(preference, "tone", None), PRESETS[Tone.STANDARD])
    settings = dict(preset)

    for key, value in (getattr(preference, "tone_overrides", None) or {}).items():
        # An override naming a setting that no longer exists, or carrying a
        # value that is no longer allowed, is ignored rather than raising — a
        # stale row from an older version must not break somebody's dashboard.
        if key in SETTINGS and value in SETTINGS[key]:
            settings[key] = value

    return settings


def describe_overdue(days: int, settings: dict) -> str:
    """One phrase, in this person's wording. The *number* is identical either
    way — §10 is explicit that nothing is withheld; only how it is said moves."""
    if settings.get("wording") == "gentle":
        return f"Moved {days} times" if days != 1 else "Moved once"
    return f"Overdue {days} days" if days != 1 else "Overdue 1 day"


def may_show_red(kind: str, settings: dict) -> bool:
    """`kind` is "overdue" or anything else. Calm never reddens a number;
    Standard reddens only genuinely overdue ones; Competitive reddens all."""
    mode = settings.get("counts_in_red", "overdue")
    if mode == "never":
        return False
    if mode == "everything":
        return True
    return kind == "overdue"
