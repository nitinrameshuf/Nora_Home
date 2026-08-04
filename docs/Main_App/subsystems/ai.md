# AI — `nora_home.ai`

## What it is

Claude, wired into the house's own data. Three model **tiers** so apps ask for a
capability rather than naming a model, a shared prompt-cached system prefix, per-call
cost accounting, and a monthly budget that refuses rather than overspends.

## Status

**Built, unproven** — Story 13. **No API key has ever been available; not one
request has been made.** Model IDs, prompt caching, and the cost arithmetic are all
unverified against the live API.

Because of that it is **not in the sidebar** (`nora_nav = False` on `AIConfig`). The
code, models, and console stay installed; the nav entry comes back when it has
actually been run against a key. An unproven feature should not be presented as a
live one.

## Models

| Model | Holds |
|---|---|
| `AIRun` | prompt, model, tier, tokens in/out, cost, duration, app_slug, member, refusal flag |

Every call is recorded, which is what makes the monthly budget enforceable and
"which app is spending the money" answerable.

## Tiers, not model IDs

| Tier | For |
|---|---|
| `catalog.FAST` | Cheap, high-volume, latency-sensitive |
| `catalog.HOUSE` | The default |
| `catalog.DEEP` | Hard reasoning, worth the money |

`catalog.py` maps tiers to model IDs in **one place**, so the house can be
re-pointed at a newer model without touching a single app. Never name a model in
app code.

## Prompt caching

The stable house prompt sits behind a `cache_control` breakpoint, so it is nearly
free after the first call in the window. **Per-app instructions go after the
breakpoint** so they never bust the shared cache. Adaptive thinking and effort are
only sent to models that accept them. `stop_reason` is checked before reading
content, so a refusal cannot crash a caller.

The system prompt states explicitly that **Nora Home is not Nora the robot**, so the
assistant never answers as though it were the robot. That is the one place the
confusion would actually mislead a person.

## What it offers other apps

`nora_home.ai.client` — `ask()`, `stream()`, `count_tokens()`, `spend_this_month()`,
and the `AIUnavailable` exception. Signatures in
[`../cross-functionality.md`](../cross-functionality.md#ai).

**Always handle `AIUnavailable`** — no key, or budget exhausted. The house degrades,
never cascades.

## Background work

| Task | Schedule | Does |
|---|---|---|
| `ask_async` | on demand | Runs a call off the request thread |

## Settings

| Key | For |
|---|---|
| `NORA_HOME_AI_ENABLED` | Master switch |
| `NORA_HOME_AI_MODEL` / `_FAST_MODEL` / `_DEEP_MODEL` | Tier → model mapping |
| `NORA_HOME_AI_MAX_TOKENS` | Default ceiling; above a threshold the client streams instead |
| `NORA_HOME_AI_EFFORT` | Reasoning effort, where the model supports it |
| `NORA_HOME_AI_MONTHLY_BUDGET_USD` | Hard cap. `_assert_budget()` refuses past it |

The API key is read from the environment only, never the database.

## Known gaps

- **Everything here is unverified.** This is the single largest untested surface in
  the platform.
- No tests (Story 21).
- The console page exists and renders, but has never returned a real answer.

## Files

```
client.py    ask, stream, count_tokens, budget enforcement
catalog.py   tier -> model mapping, pricing
models.py    AIRun
tasks.py     ask_async
views.py     console, ask, usage
```
