from django.urls import path

from nora_home.accounts import views

app_name = "accounts"

urlpatterns = [
    path("switch/", views.switch_picker, name="switch_picker"),
    path("switch/everyone/", views.switch_to_everyone, name="switch_to_everyone"),
    path("switch/<int:member_id>/", views.switch_to, name="switch_to"),
    path("logout/", views.switch_away, name="logout"),
    path("me/", views.profile, name="profile"),
    path("household/", views.household, name="household"),
]
