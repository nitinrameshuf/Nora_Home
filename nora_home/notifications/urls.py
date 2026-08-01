from django.urls import path

from nora_home.notifications import views

app_name = "notifications"

urlpatterns = [
    path("", views.inbox, name="inbox"),
    path("unread/", views.unread_count, name="unread_count"),
    path("<int:pk>/read/", views.mark_read, name="mark_read"),
    path("<int:pk>/ack/", views.acknowledge, name="acknowledge"),
]
