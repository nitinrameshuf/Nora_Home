"""
Mounted automatically at /app/habits/ — the prefix comes from `nora_slug` in
apps.py. Nothing needs adding to config/urls.py.
"""

from django.urls import path

from houseapps.example_habit import views

urlpatterns = [
    path("", views.index, name="index"),
    path("<uuid:uuid>/", views.detail, name="detail"),
    path("<uuid:uuid>/done/", views.mark_done, name="mark_done"),
]
