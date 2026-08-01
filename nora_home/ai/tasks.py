"""Run AI off the request thread. A model call must never hold a web worker."""

from __future__ import annotations

import logging

from celery import shared_task

from nora_home.ai import catalog
from nora_home.ai.client import AIUnavailable, ask

logger = logging.getLogger(__name__)


@shared_task(queue="ai", bind=True, max_retries=2, default_retry_delay=30)
def ask_async(self, prompt: str, *, context: str = "", app_slug: str = "core",
              tier: str = catalog.HOUSE, member_id: int | None = None,
              notify_member: bool = True, title: str = "The house had a thought"):
    """Ask Claude, then deliver the answer as a notification.

    House apps use this for anything the user does not need to wait for: weekly
    reviews, coaching notes, "what should I focus on tomorrow".
    """
    from nora_home.accounts.models import HouseMember

    member = HouseMember.objects.filter(pk=member_id).first() if member_id else None

    try:
        result = ask(prompt, context=context, app_slug=app_slug, tier=tier, member=member)
    except AIUnavailable as exc:
        logger.warning("AI unavailable for %s: %s", app_slug, exc)
        return {"ok": False, "error": str(exc)}

    if notify_member and member and result.text:
        from nora_home.notifications.api import notify

        notify(member, title=title, body=result.text[:1500], severity="info",
               app_slug=app_slug, icon="spark")

    return {"ok": True, "cost_usd": round(result.cost_usd, 5),
            "tokens": result.input_tokens + result.output_tokens}
