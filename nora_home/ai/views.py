from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from nora_home.ai.client import AIUnavailable, ask, spend_this_month
from nora_home.ai.models import AIRun


@login_required
def console(request):
    """A plain box to talk to Nora, plus what the house has spent this month."""
    return render(request, "ai/console.html", {
        "spend": spend_this_month(),
        "recent": AIRun.objects.select_related("member")[:20],
        "page_title": "Assistant",
    })


@login_required
@require_POST
def ask_view(request):
    prompt = (request.POST.get("prompt") or "").strip()
    if not prompt:
        return JsonResponse({"ok": False, "error": "Say something first."}, status=400)

    try:
        result = ask(prompt, app_slug="ai", member=request.user)
    except AIUnavailable as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=503)

    if result.refused:
        return JsonResponse({"ok": False, "error": "Nora declined that one."}, status=200)

    return JsonResponse({
        "ok": True,
        "text": result.text,
        "model": result.model,
        "cost_usd": round(result.cost_usd, 5),
        "duration_ms": result.duration_ms,
    })


@login_required
def usage(request):
    by_app = (AIRun.objects.values("app_slug")
              .annotate(cost=Sum("cost_usd"), tokens=Sum("output_tokens"))
              .order_by("-cost"))
    return JsonResponse({"month_to_date_usd": round(spend_this_month(), 4),
                         "by_app": list(by_app)})
