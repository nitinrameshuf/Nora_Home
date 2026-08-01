from django.contrib import admin

from nora_home.tracker.models import (
    Completion,
    EscalationEvent,
    EscalationPolicy,
    Occurrence,
    Trackable,
)


@admin.register(EscalationPolicy)
class EscalationPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "grace_minutes", "is_default", "stop_on_acknowledge")
    list_filter = ("is_default",)


class OccurrenceInline(admin.TabularInline):
    model = Occurrence
    extra = 0
    fields = ("due_at", "status", "escalation_level", "completed_by", "completed_at")
    readonly_fields = ("escalation_level",)
    ordering = ("-due_at",)


@admin.register(Trackable)
class TrackableAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "app_slug", "cadence", "next_due_at", "is_active")
    list_filter = ("app_slug", "cadence", "kind", "is_active")
    search_fields = ("title", "source_ref")
    inlines = [OccurrenceInline]


@admin.register(Occurrence)
class OccurrenceAdmin(admin.ModelAdmin):
    list_display = ("trackable", "due_at", "status", "escalation_level", "completed_by")
    list_filter = ("status", "escalation_level")
    date_hierarchy = "due_at"


@admin.register(Completion)
class CompletionAdmin(admin.ModelAdmin):
    list_display = ("created_at", "occurrence", "member", "numeric_value", "was_skip")


@admin.register(EscalationEvent)
class EscalationEventAdmin(admin.ModelAdmin):
    list_display = ("created_at", "occurrence", "level", "severity", "audience")
    list_filter = ("level", "severity", "audience")
