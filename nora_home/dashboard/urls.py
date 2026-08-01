from django.urls import path

from nora_home.dashboard import views

app_name = "dashboard"

urlpatterns = [
    path("", views.home, name="home"),
    path("catalog/", views.catalog, name="catalog"),
    path("layout/", views.save_layout, name="save_layout"),
    path("w/<str:key>/", views.widget_data, name="widget_data"),
]
