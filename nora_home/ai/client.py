"""
The house's Claude client.

House apps call `ask()` and never touch the SDK directly. That buys them: a shared
house system prompt, prompt caching on the stable prefix, cost accounting against the
monthly budget, an audit row per call, and one place to change models.

    from nora_home.ai.client import ask
    from nora_home.ai import catalog

    answer = ask(
        "Given these five workouts, what is the one thing to change next week?",
        context=recent_sessions_as_text,
        app_slug="workout",
        tier=catalog.DEEP,
    )

Nothing here raises on a missing API key — `AIUnavailable` is returned as a soft
failure so that a house app degrades to "AI is off right now" rather than a 500.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from django.conf import settings
from django.utils import timezone

from nora_home.ai import catalog

logger = logging.getLogger(__name__)

# Non-streaming requests above this risk an HTTP timeout; stream() handles the rest.
NON_STREAMING_MAX_TOKENS = 16_000


class AIUnavailable(Exception):
    """AI is not configured, over budget, or the API declined the request."""


@dataclass
class AIResult:
    text: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost_usd: float = 0.0
    duration_ms: int = 0
    stop_reason: str = ""
    refused: bool = False
    tool_calls: list = field(default_factory=list)

    def __str__(self):
        return self.text


def _client():
    """Build the SDK client lazily so the platform imports without `anthropic`."""
    if not settings.ANTHROPIC_API_KEY:
        raise AIUnavailable("ANTHROPIC_API_KEY is not set.")
    try:
        import anthropic
    except ImportError as exc:
        raise AIUnavailable("The anthropic package is not installed.") from exc
    return anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)


def house_system_prompt(extra: str = "") -> list[dict]:
    """The stable prefix every call shares — and therefore the part worth caching.

    Keep this free of timestamps, member names, and anything else that changes per
    request: caching is a prefix match, so one volatile byte here invalidates the
    cache for every app in the house.
    """
    base = (
        f"You are the assistant inside Nora Home, the house system {settings.NORA_HOME_NAME} "
        "runs on a Raspberry Pi. You help the household track habits, health, "
        "projects, maintenance, and ambitions.\n\n"
        "Nora Home is not Nora. Nora is the family's robot — a separate machine with "
        "its own voice and its own project. You are the house system it lives "
        "alongside. If someone asks about the robot, say so plainly rather than "
        "answering as though you were it.\n\n"
        "How to answer:\n"
        "- Be concrete and short. This is read on a wall display and on phones.\n"
        "- Lead with the answer, then the reasoning if it is needed at all.\n"
        "- Never invent data. If the context does not contain something, say so.\n"
        "- You are talking to a family, not to a corporation. No corporate hedging.\n"
        "- You are not a doctor. For anything medical, give general information and "
        "say plainly when something warrants a professional."
    )
    blocks = [{"type": "text", "text": base, "cache_control": {"type": "ephemeral"}}]
    if extra:
        # After the breakpoint, so per-app instructions never bust the shared cache.
        blocks.append({"type": "text", "text": extra})
    return blocks


def ask(prompt: str, *, context: str = "", app_slug: str = "core", tier: str = catalog.HOUSE,
        system_extra: str = "", max_tokens: int | None = None, member=None,
        tools: list | None = None, effort: str | None = None,
        history: list | None = None) -> AIResult:
    """One call to Claude. Returns an AIResult; raises AIUnavailable if it cannot run."""
    _assert_budget()

    model = catalog.model_for(tier)
    max_tokens = max_tokens or settings.NORA_HOME_AI_MAX_TOKENS
    if max_tokens > NON_STREAMING_MAX_TOKENS:
        logger.debug("Large max_tokens (%s); streaming instead", max_tokens)
        return stream(prompt, context=context, app_slug=app_slug, tier=tier,
                      system_extra=system_extra, max_tokens=max_tokens, member=member,
                      effort=effort, history=history)

    messages = list(history or [])
    messages.append({"role": "user", "content": _user_content(prompt, context)})

    params = {
        "model": model,
        "max_tokens": max_tokens,
        "system": house_system_prompt(system_extra),
        "messages": messages,
    }
    if catalog.supports_adaptive_thinking(model):
        params["thinking"] = {"type": "adaptive"}
        params["output_config"] = {"effort": effort or settings.NORA_HOME_AI_EFFORT}
    if tools:
        params["tools"] = tools

    started = time.monotonic()
    try:
        response = _client().messages.create(**params)
    except Exception as exc:
        logger.exception("Claude call failed for %s", app_slug)
        raise AIUnavailable(str(exc)[:300]) from exc

    result = _to_result(response, model, started)
    _record(result, app_slug=app_slug, member=member, prompt=prompt, tier=tier)
    return result


def stream(prompt: str, *, context: str = "", app_slug: str = "core",
           tier: str = catalog.HOUSE, system_extra: str = "",
           max_tokens: int = 32_000, member=None, effort: str | None = None,
           history: list | None = None, on_text=None) -> AIResult:
    """Streamed call, for long outputs. `on_text(chunk)` receives text as it arrives.

    Streaming is what keeps a long generation from hitting the HTTP timeout, so any
    call over ~16k output tokens comes through here.
    """
    _assert_budget()

    model = catalog.model_for(tier)
    messages = list(history or [])
    messages.append({"role": "user", "content": _user_content(prompt, context)})

    params = {
        "model": model,
        "max_tokens": max_tokens,
        "system": house_system_prompt(system_extra),
        "messages": messages,
    }
    if catalog.supports_adaptive_thinking(model):
        params["thinking"] = {"type": "adaptive"}
        params["output_config"] = {"effort": effort or settings.NORA_HOME_AI_EFFORT}

    started = time.monotonic()
    try:
        with _client().messages.stream(**params) as streamed:
            for chunk in streamed.text_stream:
                if on_text is not None:
                    on_text(chunk)
            response = streamed.get_final_message()
    except Exception as exc:
        logger.exception("Streamed Claude call failed for %s", app_slug)
        raise AIUnavailable(str(exc)[:300]) from exc

    result = _to_result(response, model, started)
    _record(result, app_slug=app_slug, member=member, prompt=prompt, tier=tier)
    return result


def count_tokens(prompt: str, *, context: str = "", tier: str = catalog.HOUSE,
                 system_extra: str = "") -> int:
    """How big a prompt is before sending it. Use this, never a third-party
    tokenizer — token counts are model-specific."""
    model = catalog.model_for(tier)
    response = _client().messages.count_tokens(
        model=model,
        system=house_system_prompt(system_extra),
        messages=[{"role": "user", "content": _user_content(prompt, context)}],
    )
    return response.input_tokens


def _user_content(prompt: str, context: str) -> str:
    if not context:
        return prompt
    return f"<house_data>\n{context}\n</house_data>\n\n{prompt}"


def _to_result(response, model: str, started: float) -> AIResult:
    # Check stop_reason before reading content: a refusal can come back with an
    # empty content list, and indexing it blindly would raise.
    refused = getattr(response, "stop_reason", "") == "refusal"
    text = "" if refused else "".join(
        block.text for block in response.content if getattr(block, "type", "") == "text"
    )
    tool_calls = [b for b in response.content if getattr(b, "type", "") == "tool_use"]

    usage = response.usage
    cached = getattr(usage, "cache_read_input_tokens", 0) or 0
    return AIResult(
        text=text,
        model=model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cached_tokens=cached,
        cost_usd=catalog.estimate_cost(model, usage.input_tokens, usage.output_tokens,
                                       cached),
        duration_ms=int((time.monotonic() - started) * 1000),
        stop_reason=getattr(response, "stop_reason", "") or "",
        refused=refused,
        tool_calls=tool_calls,
    )


def _record(result: AIResult, *, app_slug: str, member, prompt: str, tier: str):
    from nora_home.ai.models import AIRun

    try:
        AIRun.objects.create(
            app_slug=app_slug, member=member if getattr(member, "pk", None) else None,
            tier=tier, model=result.model, prompt=prompt[:4000],
            response=result.text[:8000], input_tokens=result.input_tokens,
            output_tokens=result.output_tokens, cached_tokens=result.cached_tokens,
            cost_usd=result.cost_usd, duration_ms=result.duration_ms,
            stop_reason=result.stop_reason, refused=result.refused,
        )
    except Exception:
        logger.exception("Could not record AI run for %s", app_slug)


def spend_this_month() -> float:
    from django.db.models import Sum

    from nora_home.ai.models import AIRun

    start = timezone.localtime().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    total = AIRun.objects.filter(created_at__gte=start).aggregate(t=Sum("cost_usd"))["t"]
    return float(total or 0)


def _assert_budget():
    """A runaway loop should cost the house one refusal, not one credit card."""
    budget = settings.NORA_HOME_AI_MONTHLY_BUDGET_USD
    if budget and spend_this_month() >= budget:
        raise AIUnavailable(
            f"The house AI budget for this month (${budget}) is spent. "
            "Raise NORA_HOME_AI_MONTHLY_BUDGET_USD to continue."
        )
