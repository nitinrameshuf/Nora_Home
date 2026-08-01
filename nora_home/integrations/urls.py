from django.urls import path

from nora_home.integrations import views

app_name = "integrations"

urlpatterns = [
    path("", views.index, name="index"),
    path("<int:pk>/", views.detail, name="detail"),
    path("<int:pk>/run/", views.run_now, name="run_now"),
]
