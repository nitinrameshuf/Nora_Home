from django.urls import path

from tests.contract_app import views

app_name = "contract_app"

urlpatterns = [
    path("", views.overview, name="overview"),
    path("history/", views.history, name="history"),
]
