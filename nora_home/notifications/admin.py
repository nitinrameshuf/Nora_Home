from django.contrib import admin

from nora_home.notifications.models import Delivery, Notification


class DeliveryInline(admin.TabularInline):
    model = Delivery
    extra = 0
    readonly_fields = ("channel", "target", "status", "attempts", "error", "sent_at",
                       "provider_ref")
    can_delete = False


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ("created_at", "severity", "app_slug", "title", "recipient", "read_at")
    list_filter = ("severity", "app_slug")
    search_fields = ("title", "body", "dedupe_key")
    date_hierarchy = "created_at"
    inlines = [DeliveryInline]


@admin.register(Delivery)
class DeliveryAdmin(admin.ModelAdmin):
    list_display = ("created_at", "channel", "target", "status", "attempts", "sent_at")
    list_filter = ("channel", "status")
