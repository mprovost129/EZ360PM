# timetracking/forms.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from django import forms

from projects.models import Project
from .models import TimeEntry


class TimeEntryForm(forms.ModelForm):
    """
    Used for manual create/edit of a single time entry.
    - Scopes the project list to the passed company (or user.active_company)
    - Computes hours if both timestamps present but hours omitted
    - Blocks negative hours
    - Optionally locks fields if the entry is already invoiced
    """
    class Meta:
        model = TimeEntry
        fields = ["project", "start_time", "end_time", "hours", "is_billable", "notes"]
        widgets = {
            "project": forms.Select(attrs={"class": "form-select"}),
            "start_time": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "end_time": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "hours": forms.NumberInput(attrs={"step": "0.01", "min": "0", "class": "form-control"}),
            "is_billable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def __init__(
        self,
        *args,
        user=None,
        company=None,
        lock_invoiced: bool = True,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)

        # Scope projects to company (prefer explicit company kwarg; fallback to user.active_company)
        scope_company = company or getattr(user, "active_company", None)
        if scope_company is not None:
            self.fields["project"].queryset = (  # type: ignore
                Project.objects.filter(company=scope_company).order_by("name")
            )

        # If editing an invoiced entry, lock most fields (still allow notes tweaks if you want)
        inst: Optional[TimeEntry] = kwargs.get("instance")
        if lock_invoiced and inst and getattr(inst, "invoice_id", None):
            for name in ("project", "start_time", "end_time", "hours", "is_billable"):
                if name in self.fields:
                    self.fields[name].disabled = True
                    self.fields[name].help_text = "Locked because this entry is on an invoice."

    def clean(self):
        data = super().clean()
        start = data.get("start_time")
        end = data.get("end_time")
        hrs = data.get("hours")

        # Basic sanity: end can't precede start
        if start and end and end < start:
            self.add_error("end_time", "End time cannot be before start time.")

        # Auto-compute hours (2-decimal) if timestamps exist but hours omitted
        if (hrs in (None, "")) and start and end:
            seconds = (end - start).total_seconds()
            if seconds > 0:
                data["hours"] = (Decimal(seconds) / Decimal(3600)).quantize(
                    Decimal("0.01"), rounding=ROUND_HALF_UP
                )

        # Guard against negative hours (can still be empty if running timer pattern)
        hrs = data.get("hours")
        if hrs is not None and hrs < 0:
            self.add_error("hours", "Hours cannot be negative.")

        return data


class TimesheetWeekForm(forms.Form):
    """
    Minimal weekly timesheet:
    - Choose week (Monday will be used server-side for range)
    - Choose project (scoped to company; if team relationship exists, prefer user’s team projects)
    - Enter decimal hours per day
    """
    week = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        label="Project",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    mon = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6, label="Mon",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
    )
    tue = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6, label="Tue",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
    )
    wed = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6, label="Wed",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
    )
    thu = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6, label="Thu",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
    )
    fri = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6, label="Fri",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
    )
    sat = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6, label="Sat",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
    )
    sun = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=6, label="Sun",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
    )

    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        help_text="Optional note applied to created/updated entries.",
    )

    def __init__(self, *args, company=None, user=None, **kwargs):
        super().__init__(*args, **kwargs)

        qs = Project.objects.none()
        if company is not None:
            base = Project.objects.filter(company=company).order_by("-created_at")
            if user is not None:
                # If Project has a ManyToMany "team" to users, prefer those
                team_qs = base.filter(team=user).distinct() if hasattr(Project, "team") else Project.objects.none()
                qs = team_qs if team_qs.exists() else base
            else:
                qs = base
        self.fields["project"].queryset = qs  # type: ignore

    def clean(self):
        data = super().clean()
        # At least one day should have hours (optional—but nice UX)
        day_fields = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
        if not any(data.get(d) for d in day_fields):
            self.add_error(None, "Enter hours for at least one day.")
        return data


class TimesheetSubmitForm(forms.Form):
    """
    Basic form to submit a week's timesheet for approval.
    """
    week = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    confirm = forms.BooleanField(
        required=True,
        initial=False,
        label="I confirm this timesheet is complete and accurate.",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    note = forms.CharField(
        required=False,
        label="Note to approver (optional)",
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
    )
