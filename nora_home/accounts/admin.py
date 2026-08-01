from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from nora_home.accounts.models import EscalationContact, HouseMember


class EscalationContactInline(admin.TabularInline):
    model = EscalationContact
    fk_name = "member"
    extra = 1


@admin.register(HouseMember)
class HouseMemberAdmin(UserAdmin):
    inlines = [EscalationContactInline]
    list_display = ("username", "display_name", "role", "notifications_enabled",
                    "is_on_wall_display")
    list_filter = ("role", "notifications_enabled", "is_on_wall_display")
    fieldsets = UserAdmin.fieldsets + (
        ("House", {"fields": ("display_name", "role", "avatar", "accent_color",
                              "birthday", "timezone", "is_on_wall_display")}),
        ("Contact", {"fields": ("slack_user_id", "slack_dm_channel", "phone")}),
        ("Notifications", {"fields": ("notifications_enabled", "preferred_channels",
                                      "quiet_hours_start", "quiet_hours_end")}),
    )
