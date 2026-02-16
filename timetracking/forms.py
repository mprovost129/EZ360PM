from __future__ import annotations

from datetime import datetime
from typing import Optional

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from companies.models import EmployeeProfile
from projects.models import Project
from catalog.models import CatalogItem
from catalog.models import CatalogItemType

from .models import TimeEntry, TimeEntryService, TimeStatus, TimeTrackingSettings, TimeEntryMode, ClockFormat


class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = [
            "project",
            "started_at",
            "ended_at",
            "duration_minutes",
            "billable",
            "note",
        ]
        widgets = {
            "started_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "ended_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "duration_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
            "note": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "billable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "project": forms.Select(attrs={"class": "form-select"}),
        }

    def clean(self):
        cleaned = super().clean()
        started_at = cleaned.get("started_at")
        ended_at = cleaned.get("ended_at")
        duration = cleaned.get("duration_minutes") or 0

        if started_at and ended_at and ended_at < started_at:
            self.add_error("ended_at", "End time must be after start time.")

        if duration < 0:
            self.add_error("duration_minutes", "Duration must be 0 or greater.")

        if not duration and started_at and ended_at:
            minutes = int((ended_at - started_at).total_seconds() // 60)
            cleaned["duration_minutes"] = max(0, minutes)

        return cleaned


TimeEntryServiceFormSet = inlineformset_factory(
    TimeEntry,
    TimeEntryService,
    fields=["catalog_item", "name", "minutes"],
    extra=1,
    can_delete=True,
    widgets={
        "catalog_item": forms.Select(attrs={"class": "form-select"}),
        "name": forms.TextInput(attrs={"class": "form-control"}),
        "minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0}),
    },
)


class TimeFilterForm(forms.Form):
    PRESETS = (
        ("today", "Today"),
        ("yesterday", "Yesterday"),
        ("last7", "Last 7 days"),
        ("thismonth", "This month"),
        ("lastmonth", "Last month"),
        ("custom", "Custom"),
    )

    preset = forms.ChoiceField(choices=PRESETS, required=False, widget=forms.Select(attrs={"class": "form-select form-select-sm"}))
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control form-control-sm"}))
    q = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "form-control form-control-sm", "placeholder": "Search note / project / client"}))
    status = forms.ChoiceField(
        required=False,
        choices=(("", "All statuses"),) + tuple(TimeStatus.choices),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )
    billable = forms.ChoiceField(
        required=False,
        choices=(("", "Billable + non-billable"), ("1", "Billable"), ("0", "Non-billable")),
        widget=forms.Select(attrs={"class": "form-select form-select-sm"}),
    )


class TimerStartForm(forms.Form):
    project = forms.ModelChoiceField(queryset=Project.objects.none(), required=False, widget=forms.Select(attrs={"class": "form-select"}))
    service_catalog_item = forms.ModelChoiceField(
        queryset=CatalogItem.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": "form-select"}),
        label="Service",
    )
    service_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Or type a custom service"}),
        label="Custom service",
    )
    note = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "form-control", "rows": 2}))

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["project"] = forms.ModelChoiceField(
                queryset=Project.objects.filter(company=company, deleted_at__isnull=True).order_by("project_number", "name"),
                required=False,
                widget=forms.Select(attrs={"class": "form-select"})
            )

            self.fields["service_catalog_item"].queryset = CatalogItem.objects.filter(
                company=company,
                item_type=CatalogItemType.SERVICE,
                is_active=True,
                deleted_at__isnull=True,
            ).order_by("name")

    def clean(self):
        cleaned = super().clean()
        # If a catalog service is selected, we ignore the custom service name.
        if cleaned.get("service_catalog_item"):
            cleaned["service_name"] = ""
        return cleaned


class TimeSettingsForm(forms.ModelForm):
    class Meta:
        model = TimeTrackingSettings
        fields = ["entry_mode", "clock_format", "rounding_minutes", "require_manager_approval"]
        widgets = {
            "entry_mode": forms.Select(attrs={"class": "form-select"}),
            "clock_format": forms.Select(attrs={"class": "form-select"}),
            "rounding_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0, "step": 1}),
            "require_manager_approval": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
