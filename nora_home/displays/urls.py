from django.urls import path

from nora_home.displays import views

app_name = "displays"

urlpatterns = [
    path("", views.manage, name="manage"),
    path("wall/", views.wall, name="wall"),
    path("wall/<slug:slug>/", views.wall, name="wall_named"),
    path("kiosk/", views.kiosk, name="kiosk"),
    path("status/", views.status, name="status"),
    path("<slug:slug>/command/", views.command, name="command"),
]
