from django.urls import path

from nora_home.tracker import views

app_name = "tracker"

urlpatterns = [
    path("", views.board, name="board"),
    path("house/", views.house_board, name="house_board"),
    path("t/<uuid:uuid>/", views.trackable_detail, name="detail"),
    path("o/<uuid:uuid>/complete/", views.complete, name="complete"),
    path("o/<uuid:uuid>/skip/", views.skip, name="skip"),
    path("o/<uuid:uuid>/ack/", views.acknowledge, name="acknowledge"),
]
