from django.contrib import admin

from nora_home.displays.models import Display, DisplayCommand


@admin.register(Display)
class DisplayAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "kind", "is_online", "location", "last_seen_at")
    list_filter = ("kind", "is_active")


@admin.register(DisplayCommand)
class DisplayCommandAdmin(admin.ModelAdmin):
    list_display = ("created_at", "display", "action", "issued_by")
    list_filter = ("action", "display")
    date_hierarchy = "created_at"
