from django.contrib import admin

from nora_home.telemetry.models import HourlyRollup, Reading, Series


@admin.register(Series)
class SeriesAdmin(admin.ModelAdmin):
    list_display = ("key", "label", "unit", "app_slug", "member", "latest_value",
                    "show_on_wall", "is_active")
    list_filter = ("app_slug", "direction", "show_on_wall", "is_active")
    search_fields = ("key", "label")


@admin.register(Reading)
class ReadingAdmin(admin.ModelAdmin):
    list_display = ("recorded_at", "series", "value", "member", "source")
    list_filter = ("source", "series")
    date_hierarchy = "recorded_at"


@admin.register(HourlyRollup)
class HourlyRollupAdmin(admin.ModelAdmin):
    list_display = ("hour", "series", "count", "mean", "minimum", "maximum")
    date_hierarchy = "hour"
