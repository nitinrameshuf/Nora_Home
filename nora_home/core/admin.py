from django.contrib import admin

from nora_home.core.models import AuditEvent, DeviceToken, HouseSetting, SystemHealthSnapshot


@admin.register(HouseSetting)
class HouseSettingAdmin(admin.ModelAdmin):
    list_display = ("key", "app_slug", "description", "updated_at")
    list_filter = ("app_slug",)
    search_fields = ("key", "description")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "app_slug", "action", "severity", "actor", "subject")
    list_filter = ("severity", "app_slug", "source")
    search_fields = ("action", "subject")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AuditEvent._meta.fields]

    def has_add_permission(self, request):
        return False


@admin.register(SystemHealthSnapshot)
class SystemHealthSnapshotAdmin(admin.ModelAdmin):
    list_display = ("created_at", "healthy", "cpu_temp_c", "disk_percent")
    list_filter = ("healthy",)
    date_hierarchy = "created_at"


@admin.register(DeviceToken)
class DeviceTokenAdmin(admin.ModelAdmin):
    list_display = ("name", "prefix", "member", "last_used_at", "revoked_at")
    readonly_fields = ("token_hash", "prefix", "last_used_at")
    search_fields = ("name",)
