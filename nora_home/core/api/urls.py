"""
Platform API.

House apps expose their own API by adding DRF routes to their urls.py; they are
reachable under /app/<slug>/api/... . This module is only for platform-level
endpoints that every client needs.
"""

from django.urls import path

from nora_home.core.api import views

app_name = "api"

urlpatterns = [
    path("health/", views.HealthView.as_view(), name="health"),
    path("apps/", views.AppListView.as_view(), name="apps"),
    path("whoami/", views.WhoAmIView.as_view(), name="whoami"),
    path("homebot/say/", views.HomeBotSayView.as_view(), name="homebot_say"),
]
