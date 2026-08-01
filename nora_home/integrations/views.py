from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_POST

from nora_home.integrations.base import available
from nora_home.integrations.models import Integration
from nora_home.integrations.tasks import run_integration


@login_required
def index(request):
    return render(request, "integrations/index.html", {
        "integrations": Integration.objects.all(),
        "catalog": [
            {"slug": slug, "name": klass.name or slug,
             "description": klass.description, "icon": klass.icon}
            for slug, klass in sorted(available().items())
        ],
        "page_title": "Integrations",
    })


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
