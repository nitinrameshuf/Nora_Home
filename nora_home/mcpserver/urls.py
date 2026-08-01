from django.urls import path

from nora_home.mcpserver import views

app_name = "mcp"

urlpatterns = [
    path("tools/", views.list_tools, name="tools"),
    path("call/", views.call_tool, name="call"),
]
