from django.contrib import admin

from nora_home.integrations.models import Integration, IntegrationRun


@admin.register(Integration)
class IntegrationAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "is_enabled", "interval_minutes",
                    "last_success_at", "consecutive_failures")
    list_filter = ("slug", "is_enabled")
    readonly_fields = ("last_run_at", "last_success_at", "consecutive_failures",
                       "last_error")


@admin.register(IntegrationRun)
class IntegrationRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "integration", "succeeded", "duration_ms")
    list_filter = ("succeeded", "integration")
    date_hierarchy = "created_at"
