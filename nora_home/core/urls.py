"""
The base app, mounted at /home/.

The home screen itself is the dashboard app's — it is the grid of visualizations
each person arranges — but it keeps the name `core:dashboard` because that is what
everything reverses against.
"""

from django.urls import path

from nora_home.core import views
from nora_home.dashboard import views as dashboard_views

app_name = "core"

urlpatterns = [
    path("", dashboard_views.home, name="dashboard"),
    path("system/", views.system_status, name="system_status"),
    path("styleguide/", views.styleguide, name="styleguide"),
    path("log/", views.house_log, name="house_log"),
    path("settings/", views.settings_page, name="settings"),
    path("health/", views.health, name="health"),
    path("api/weather/", views.weather_current, name="weather_current"),
]
