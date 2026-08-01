from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from nora_home.accounts.models import HouseMember


@login_required
def profile(request):
    return render(request, "accounts/profile.html", {
        "member": request.user,
        "chain": request.user.escalation_chain(),
        "page_title": "You",
    })


@login_required
def household(request):
    return render(request, "accounts/household.html", {
        "members": HouseMember.objects.filter(is_active=True),
        "page_title": "Household",
    })
