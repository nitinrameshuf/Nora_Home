from __future__ import annotations

from dataclasses import asdict

from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from nora_home.core.health import collect_health
from nora_home.core.registry import registered_apps


class HealthView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        report = collect_health()
        return Response(report, status=200 if report["healthy"] else 503)


class AppListView(APIView):
    def get(self, request):
        return Response({"apps": [asdict(m) for m in registered_apps()]})


class WhoAmIView(APIView):
    def get(self, request):
        user = request.user
        return Response({
            "username": user.get_username(),
            "display_name": getattr(user, "display_name", "") or user.get_username(),
            "role": getattr(user, "role", "member"),
            "surface": getattr(request, "nh_surface", "web"),
        })


class HomeBotSayView(APIView):
    """Make the home bot speak on a surface.

    Used by house apps, and by Nora the robot when it wants to put something on the
    house's screens — which is the one place the two systems deliberately meet.
    """

    def post(self, request):
        from nora_home.ui import bot

        bot.say(
            message=str(request.data.get("message", ""))[:280],
            mood=str(request.data.get("mood", "happy")),
            surface=str(request.data.get("surface", "all")),
        )
        return Response({"ok": True})
