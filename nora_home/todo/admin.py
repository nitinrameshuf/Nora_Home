from django.contrib import admin

from nora_home.todo.models import (
    Attachment,
    ChangeEvent,
    Comment,
    Event,
    Instance,
    Label,
    Link,
    Reminder,
    Task,
    TodoPreference,
)


class InstanceInline(admin.TabularInline):
    model = Instance
    extra = 0
    fields = ("due_at", "outcome", "completed_by", "completed_at", "actual_minutes",
              "approved_by", "approved_at")
    ordering = ("-due_at",)


class ChangeEventInline(admin.TabularInline):
    model = ChangeEvent
    extra = 0
    fields = ("field", "from_value", "to_value", "actor", "created_at")
    readonly_fields = ("created_at",)
    ordering = ("-created_at",)


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "shared_with", "approver", "priority",
                    "state", "source", "due_on")
    list_filter = ("state", "priority", "source", "escalation_enabled")
    search_fields = ("title", "description")
    filter_horizontal = ("labels", "assignees")
    inlines = [InstanceInline, ChangeEventInline]

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("assignees")

    @admin.display(description="Shared with")
    def shared_with(self, obj):
        return ", ".join(str(m) for m in obj.assignees.all()) or "—"


@admin.register(Instance)
class InstanceAdmin(admin.ModelAdmin):
    list_display = ("task", "due_at", "outcome", "completed_by", "completed_at",
                    "approved_by")
    list_filter = ("outcome",)
    date_hierarchy = "due_at"


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "starts_at", "all_day", "recurrence")
    list_filter = ("recurrence", "all_day")
    date_hierarchy = "starts_at"


@admin.register(Label)
class LabelAdmin(admin.ModelAdmin):
    list_display = ("name", "colour")
    search_fields = ("name",)


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "author", "created_at")
    date_hierarchy = "created_at"


@admin.register(Attachment)
class AttachmentAdmin(admin.ModelAdmin):
    list_display = ("__str__", "uploaded_by", "created_at")
    date_hierarchy = "created_at"


@admin.register(Link)
class LinkAdmin(admin.ModelAdmin):
    list_display = ("__str__", "is_internal", "created_at")


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display = ("__str__", "offset_minutes", "absolute_at", "channels")


@admin.register(ChangeEvent)
class ChangeEventAdmin(admin.ModelAdmin):
    list_display = ("task", "field", "from_value", "to_value", "actor", "created_at")
    list_filter = ("field",)
    date_hierarchy = "created_at"


@admin.register(TodoPreference)
class TodoPreferenceAdmin(admin.ModelAdmin):
    list_display = ("member", "default_due_hour", "tone")
    list_filter = ("tone",)
