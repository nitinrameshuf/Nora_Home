from django.urls import path

from nora_home.ai import views

app_name = "ai"

urlpatterns = [
    path("", views.console, name="console"),
    path("ask/", views.ask_view, name="ask"),
    path("usage/", views.usage, name="usage"),
]
