from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from nora_home.notifications.models import Notification


def _visible_to(user):
    return Notification.objects.filter(Q(recipient=user) | Q(recipient__isnull=True))


@login_required
def inbox(request):
    return render(request, "notifications/inbox.html", {
        "notifications": _visible_to(request.user).select_related("recipient")[:100],
        "page_title": "Alerts",
    })


@login_required
def unread_count(request):
    count = _visible_to(request.user).filter(read_at__isnull=True).count()
    return JsonResponse({"unread": count})


@login_required
@require_POST
def mark_read(request, pk: int):
    notification = get_object_or_404(_visible_to(request.user), pk=pk)
    if notification.read_at is None:
        notification.read_at = timezone.now()
        notification.save(update_fields=["read_at"])
    if request.headers.get("X-Requested-With") == "fetch":
        return JsonResponse({"ok": True})
    return redirect(notification.url or "notifications:inbox")


@login_required
@require_POST
def acknowledge(request, pk: int):
    """Acknowledging stops the escalation ladder for the item behind this alert."""
    notification = get_object_or_404(_visible_to(request.user), pk=pk)
    notification.acknowledged_at = timezone.now()
    notification.acknowledged_by = request.user
    notification.read_at = notification.read_at or timezone.now()
    notification.save(update_fields=["acknowledged_at", "acknowledged_by", "read_at"])
    return JsonResponse({"ok": True})
