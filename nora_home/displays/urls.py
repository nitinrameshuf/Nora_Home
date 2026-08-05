from django.urls import path

from nora_home.displays import views

app_name = "displays"

urlpatterns = [
    path("", views.manage, name="manage"),
    path("wall/", views.wall, name="wall"),
    path("wall/<slug:slug>/", views.wall, name="wall_named"),
    path("kiosk/", views.kiosk, name="kiosk"),
    path("status/", views.status, name="status"),
    # "command/<slug>/" rather than "<slug>/command/": the latter is ambiguous
    # with "wall/<slug>/" above, and Django resolves in order — so
    # /home/displays/wall/command/ matched wall_named(slug="command") and the
    # command endpoint was unreachable for the one display the kiosk actually
    # targets. Putting the literal segment first removes the ambiguity instead
    # of depending on which line comes earlier.
    path("command/<slug:slug>/", views.command, name="command"),
]
