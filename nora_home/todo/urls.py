from django.urls import path

from nora_home.todo import views

app_name = "todo"

urlpatterns = [
    path("", views.board, name="board"),
    path("new/", views.create, name="create"),
    path("t/<uuid:uuid>/", views.detail, name="detail"),
    path("t/<uuid:uuid>/edit/", views.edit, name="edit"),
    path("t/<uuid:uuid>/archive/", views.archive, name="archive"),
    path("t/<uuid:uuid>/restore/", views.restore, name="restore"),
    path("t/<uuid:uuid>/delete/", views.delete, name="delete"),
    path("i/<uuid:uuid>/complete/", views.complete, name="complete"),
    path("i/<uuid:uuid>/uncomplete/", views.uncomplete, name="uncomplete"),
    path("i/<uuid:uuid>/skip/", views.skip, name="skip"),
    path("i/<uuid:uuid>/approve/", views.approve, name="approve"),
    path("i/<uuid:uuid>/reject/", views.reject, name="reject"),
    path("i/<uuid:uuid>/ack/", views.acknowledge, name="acknowledge"),
]
