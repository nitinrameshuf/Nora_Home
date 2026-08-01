from django.urls import path

from nora_home.telemetry import views

app_name = "telemetry"

urlpatterns = [
    path("", views.index, name="index"),
    path("<str:key>/", views.detail, name="detail"),
    path("<str:key>/history/", views.history, name="history"),
    path("<str:key>/record/", views.record, name="record"),
]
