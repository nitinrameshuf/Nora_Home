"""
Root URL map.

Two rules:

    /home/...        the platform — settings, tracker, alerts, displays, AI, system
    /<app-slug>/...  each house app gets a top-level URL of its own

So the family's apps read like their own sites — /workout, /family, /maintenance —
while everything belonging to the base system stays tucked under /home. Apps are
mounted automatically from nora_home.core.registry; you never edit this file to add one.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from nora_home.core.registry import house_app_urlpatterns

urlpatterns = [
    # The base app.
    path("home/", include("nora_home.core.urls")),
    path("home/tracker/", include("nora_home.tracker.urls")),
    path("home/alerts/", include("nora_home.notifications.urls")),
    path("home/displays/", include("nora_home.displays.urls")),
    path("home/ai/", include("nora_home.ai.urls")),
    path("home/measurements/", include("nora_home.telemetry.urls")),
    path("home/integrations/", include("nora_home.integrations.urls")),
    path("home/dashboard/", include("nora_home.dashboard.urls")),

    # Todo is Level 2 (docs/Main_App/subsystems/todo.md §1) — a platform app, so
    # house_app_urlpatterns() below skips it, but it still lives at its own
    # top-level slug like a house app would rather than under /home/.
    path("todo/", include("nora_home.todo.urls")),

    # Cross-cutting surfaces, deliberately outside /home so their URLs stay short.
    path("accounts/", include("nora_home.accounts.urls")),
    path("api/", include("nora_home.core.api.urls")),
    path("mcp/", include("nora_home.mcpserver.urls")),
    path("admin/", admin.site.urls),

    # The bare domain lands on the home dashboard.
    path("", RedirectView.as_view(pattern_name="core:dashboard", permanent=False)),
]

# Everything under houseapps/ mounts at its own top-level slug.
urlpatterns += house_app_urlpatterns()

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler404 = "nora_home.core.views.not_found"
handler500 = "nora_home.core.views.server_error"
