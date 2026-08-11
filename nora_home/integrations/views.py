from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from nora_home.integrations.models import Integration
from nora_home.integrations.tasks import run_integration


@login_required
def index(request):
    """Retired 2026-08-10 (Story 55) — Integrations is a System tab now, not
    its own destination: the mockup's System page (SYS_VIEWS.integrations)
    never had a standalone one, only the four tabs. Kept as a redirect so an
    old bookmark or nav link still lands somewhere real."""
    return redirect(f"{reverse('core:system_status')}?tab=integrations")


@login_required
def detail(request, pk: int):
    integration = get_object_or_404(Integration, pk=pk)
    return render(request, "integrations/detail.html", {
        "integration": integration,
        "runs": integration.runs.all()[:30],
        "page_title": integration.name,
    })


@login_required
@require_POST
def run_now(request, pk: int):
    integration = get_object_or_404(Integration, pk=pk)
    run_integration.apply_async(args=[integration.pk], queue="integrations")
    return JsonResponse({"ok": True, "queued": integration.name})
