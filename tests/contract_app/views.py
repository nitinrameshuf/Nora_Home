from django.contrib.auth.decorators import login_required
from django.http import HttpResponse


@login_required
def overview(request):
    return HttpResponse("contract app: overview")


@login_required
def history(request):
    return HttpResponse("contract app: history")
