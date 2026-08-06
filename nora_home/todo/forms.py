"""
The create/edit form. One page, one form — Todo has no wizard.

`recurrence_spec` is assembled here from a handful of plain fields rather than
exposed as raw JSON: nobody creating a task should have to know the shape
documented in `nora_home.todo.recurrence`.
"""

from __future__ import annotations

from django import forms

from nora_home.todo.models import Label, Priority, RecurrenceType, Task

WEEKDAY_CHOICES = [(0, "Mon"), (1, "Tue"), (2, "Wed"), (3, "Thu"),
                   (4, "Fri"), (5, "Sat"), (6, "Sun")]

FIXED_KIND_CHOICES = [
    ("daily", "Every day"), ("weekdays", "Weekdays"), ("weekly", "Weekly"),
    ("monthly", "Monthly"), ("yearly", "Yearly"), ("interval", "Every N days"),
]


class TaskForm(forms.ModelForm):
    labels = forms.ModelMultipleChoiceField(
        queryset=Label.objects.all(), required=False,
        widget=forms.CheckboxSelectMultiple)
    assignees = forms.ModelMultipleChoiceField(
        queryset=None, required=False, widget=forms.CheckboxSelectMultiple,
        help_text="Who can do it. Any one of them closes it. Leave empty to "
                  "keep it just the owner's.")

    # Recurrence, expanded into plain fields rather than raw JSON.
    recurrence_kind = forms.ChoiceField(choices=FIXED_KIND_CHOICES, required=False)
    recurrence_weekdays = forms.MultipleChoiceField(
        choices=WEEKDAY_CHOICES, required=False, widget=forms.CheckboxSelectMultiple)
    recurrence_day = forms.IntegerField(required=False, min_value=1, max_value=31)
    recurrence_month = forms.IntegerField(required=False, min_value=1, max_value=12)
    recurrence_interval_days = forms.IntegerField(required=False, min_value=1)
    recurrence_ends_on = forms.DateField(required=False)

    class Meta:
        model = Task
        fields = [
            "title", "description", "priority", "owner", "labels",
            "assignees", "approver", "due_on", "due_time", "deadline_firm",
            "planned_minutes", "recurrence_type", "escalation_enabled",
            "escalation_policy", "alarm_kind", "alarm_ref",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 4}),
            "priority": forms.RadioSelect,
        }

    def __init__(self, *args, house_members=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["priority"].choices = Priority.choices
        self.fields["priority"].required = True
        if house_members is not None:
            self.fields["owner"].queryset = house_members
            self.fields["assignees"].queryset = house_members
            self.fields["approver"].queryset = house_members
        self.fields["approver"].required = False
        self.fields["escalation_policy"].required = False

        if self.instance and self.instance.pk:
            spec = self.instance.recurrence_spec or {}
            self.fields["recurrence_kind"].initial = spec.get("kind", "daily")
            self.fields["recurrence_weekdays"].initial = spec.get("weekdays", [])
            self.fields["recurrence_day"].initial = spec.get("day")
            self.fields["recurrence_month"].initial = spec.get("month")
            self.fields["recurrence_interval_days"].initial = spec.get("days")
            self.fields["recurrence_ends_on"].initial = spec.get("ends_on")

    def clean(self):
        cleaned = super().clean()
        # The recurring-task-cannot-have-an-approver rule is *not* re-checked
        # here: ModelForm._post_clean() already runs Task.clean() against this
        # same cleaned data and attaches its error to the "approver" field
        # automatically. Checking it twice would just double the message.
        cleaned["recurrence_spec"] = self._build_recurrence_spec(
            cleaned, cleaned.get("recurrence_type"))
        return cleaned

    def _build_recurrence_spec(self, cleaned, recurrence_type) -> dict:
        spec: dict = {}
        if recurrence_type == RecurrenceType.FIXED:
            kind = cleaned.get("recurrence_kind") or "daily"
            spec["kind"] = kind
            if kind == "weekly" and cleaned.get("recurrence_weekdays"):
                spec["weekdays"] = [int(d) for d in cleaned["recurrence_weekdays"]]
            if kind in ("monthly", "yearly") and cleaned.get("recurrence_day"):
                spec["day"] = cleaned["recurrence_day"]
            if kind == "yearly" and cleaned.get("recurrence_month"):
                spec["month"] = cleaned["recurrence_month"]
            if kind == "interval":
                spec["days"] = cleaned.get("recurrence_interval_days") or 1
        elif recurrence_type == RecurrenceType.ROLLING:
            spec["days"] = cleaned.get("recurrence_interval_days") or 1
        if cleaned.get("recurrence_ends_on"):
            spec["ends_on"] = cleaned["recurrence_ends_on"].isoformat()
        return spec

    def save(self, commit=True):
        task = super().save(commit=False)
        task.recurrence_spec = self.cleaned_data.get("recurrence_spec", {})
        if commit:
            task.save()
            self.save_m2m()
        return task
