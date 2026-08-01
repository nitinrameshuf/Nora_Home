from django.contrib import admin

from houseapps.example_habit.models import Habit


@admin.register(Habit)
class HabitAdmin(admin.ModelAdmin):
    list_display = ("title", "owner", "cadence", "due_time", "is_active")
    list_filter = ("cadence", "is_active", "owner")
    search_fields = ("title", "why")
