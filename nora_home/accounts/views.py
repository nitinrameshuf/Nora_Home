from django.conf import settings
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from nora_home.accounts.models import HouseMember

SCOPE_SESSION_KEY = "nh_view_scope"


def _safe_next(request) -> str:
    # Mirrors Django's own LoginView.get_success_url(): trust ?next=/next= only
    # if it points somewhere local, so a crafted link can't bounce someone off
    # this house onto an attacker's site after they tap their name.
    candidate = request.POST.get("next") or request.GET.get("next") or ""
    if candidate and url_has_allowed_host_and_scheme(
        candidate, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return candidate
    return ""


def switch_picker(request):
    """Tap a name to become them. No password, anywhere in this house."""
    return render(request, "accounts/switch.html", {
        "members": HouseMember.objects.filter(is_active=True),
        "next": _safe_next(request),
        "page_title": "Who's this?",
    })


@require_POST
def switch_to(request, member_id):
    member = get_object_or_404(HouseMember, pk=member_id, is_active=True)
    auth_login(request, member, backend="django.contrib.auth.backends.ModelBackend")
    request.session[SCOPE_SESSION_KEY] = "self"
    return redirect(_safe_next(request) or settings.LOGIN_REDIRECT_URL)


@require_POST
def switch_to_everyone(request):
    if not request.user.is_authenticated:
        # login_required, the admin, and CSRF all need a real request.user even in
        # combined mode — fall back to whoever sorts first, invisibly.
        fallback = HouseMember.objects.filter(is_active=True).first()
        if fallback is None:
            raise Http404("No household members yet — run `make member` first.")
        auth_login(request, fallback,
                  backend="django.contrib.auth.backends.ModelBackend")
    request.session[SCOPE_SESSION_KEY] = "all"
    return redirect(_safe_next(request) or settings.LOGIN_REDIRECT_URL)


@login_required
def switch_away(request):
    """'Sign out' in a house with no passwords just means: ask again."""
    auth_logout(request)
    return redirect("accounts:switch_picker")


@login_required
def profile(request):
    """Folded into core:settings — kept as a redirect so old links still land."""
    return redirect("core:settings")


@login_required
def household(request):
    return render(request, "accounts/household.html", {
        "members": HouseMember.objects.filter(is_active=True),
        "page_title": "Household",
    })
