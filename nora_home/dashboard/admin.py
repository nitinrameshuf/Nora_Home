from django.contrib import admin

from nora_home.dashboard.models import DashboardLayout


@admin.register(DashboardLayout)
class DashboardLayoutAdmin(admin.ModelAdmin):
    list_display = ("name", "member", "surface", "widget_count", "updated_at")
    list_filter = ("surface",)

    @admin.display(description="Widgets")
    def widget_count(self, obj):
        return len(obj.items)
