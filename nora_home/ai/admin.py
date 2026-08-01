from django.contrib import admin

from nora_home.ai.models import AIRun


@admin.register(AIRun)
class AIRunAdmin(admin.ModelAdmin):
    list_display = ("created_at", "app_slug", "model", "member", "cost_usd",
                    "duration_ms", "refused")
    list_filter = ("app_slug", "model", "tier", "refused")
    search_fields = ("prompt", "response")
    date_hierarchy = "created_at"
    readonly_fields = [f.name for f in AIRun._meta.fields]

    def has_add_permission(self, request):
        return False
