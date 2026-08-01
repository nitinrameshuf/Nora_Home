"""
Which Claude model to use, and what it costs.

Three tiers, so a house app asks for a capability rather than hard-coding a model
string. Change the mapping in one place (or in .env) and every app follows.

    FAST  — classification, extraction, one-line summaries. Cheap, quick.
    HOUSE — the default. Planning, coaching, drafting, analysis.
    DEEP  — long-horizon reasoning, whole-week reviews, hard debugging.
"""

from __future__ import annotations

from django.conf import settings

FAST = "fast"
HOUSE = "house"
DEEP = "deep"


def model_for(tier: str = HOUSE) -> str:
    return {
        FAST: settings.NORA_HOME_AI_FAST_MODEL,
        HOUSE: settings.NORA_HOME_AI_MODEL,
        DEEP: settings.NORA_HOME_AI_DEEP_MODEL,
    }.get(tier, settings.NORA_HOME_AI_MODEL)


# USD per million tokens, for the house AI budget. Update when pricing moves.
PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-fable-5": (10.00, 50.00),
}

# Models that take adaptive thinking and the effort parameter. Passing either to an
# older model is an API error, so the client checks this before adding them.
ADAPTIVE_THINKING_MODELS = {
    "claude-opus-5", "claude-sonnet-5", "claude-fable-5",
    "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6", "claude-sonnet-4-6",
}

# Cheapest cacheable prefix, in tokens. Below this, cache_control does nothing.
CACHE_MINIMUM_TOKENS = {"claude-opus-5": 512, "claude-fable-5": 512}
DEFAULT_CACHE_MINIMUM = 1024


def supports_adaptive_thinking(model: str) -> bool:
    return model in ADAPTIVE_THINKING_MODELS


def estimate_cost(model: str, input_tokens: int, output_tokens: int,
                  cached_read_tokens: int = 0) -> float:
    """USD for one call. Cache reads bill at roughly a tenth of the input rate."""
    rates = PRICING.get(model)
    if rates is None:
        return 0.0
    in_rate, out_rate = rates
    return (
        input_tokens / 1_000_000 * in_rate
        + cached_read_tokens / 1_000_000 * in_rate * 0.1
        + output_tokens / 1_000_000 * out_rate
    )
