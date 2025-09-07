# projects/forms.py
from typing import Optional

from django import forms
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from clients.models import Client
from company.models import Company, CompanyMember

from .models import Project


class ProjectForm(forms.ModelForm):
    """Project form (pass `company=` to scope choices and validate number uniqueness per company)."""

    class Meta:
        model = Project
        fields = [
            "number", "name", "client", "billing_type", "details",
            "budget", "estimated_hours", "hourly_rate",
            "start_date", "due_date", "team",
        ]
        widgets = {
            "number": forms.TextInput(attrs={
                "class": "form-control",
                "placeholder": "Optional internal ID (e.g. 2025-010)",
                "autocomplete": "off",
            }),
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Project name"}),
            "client": forms.Select(attrs={"class": "form-select"}),
            "billing_type": forms.Select(attrs={"class": "form-select"}),
            "details": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "budget": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "estimated_hours": forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
            "hourly_rate": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "team": forms.SelectMultiple(attrs={"class": "form-select", "size": "6"}),
        }

    def __init__(self, *args, **kwargs):
        self._company: Optional[Company] = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)

        # Make project number optional at the form level (so leaving it blank is allowed)
        self.fields["number"].required = False
        self.fields["number"].help_text = _("Leave blank to auto-generate.")  # type: ignore[attr-defined]

        # Scope selects to the active company
        if self._company:
            self.fields["client"].queryset = (  # type: ignore[attr-defined]
                Client.objects.filter(company=self._company).order_by("org", "last_name")
            )
            member_ids = CompanyMember.objects.filter(company=self._company).values_list("user_id", flat=True)
            self.fields["team"].queryset = (  # type: ignore[attr-defined]
                get_user_model().objects.filter(id__in=member_ids).order_by("email")
            )

        # Helpful empty labels
        self.fields["client"].empty_label = "— Select client —"  # type: ignore[attr-defined]

    # -----------------------
    # Field-level validation
    # -----------------------
    def clean_number(self):
        """
        If number is provided, enforce uniqueness within the company.
        If left blank, model.save() will auto-generate it.
        """
        number = (self.cleaned_data.get("number") or "").strip()
        if number and self._company:
            qs = Project.objects.filter(company=self._company, number__iexact=number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(_("A project with this number already exists in your company."))
        return number

    def clean_budget(self):
        val = self.cleaned_data.get("budget")
        if val is not None and val < 0:
            raise ValidationError(_("Budget must be ≥ 0."))
        return val

    def clean_estimated_hours(self):
        val = self.cleaned_data.get("estimated_hours")
        if val is not None and val < 0:
            raise ValidationError(_("Estimated hours must be ≥ 0."))
        return val

    def clean_hourly_rate(self):
        val = self.cleaned_data.get("hourly_rate")
        if val is not None and val < 0:
            raise ValidationError(_("Hourly rate must be ≥ 0."))
        return val

    # -----------------------
    # Form-level validation
    # -----------------------
    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        due = cleaned.get("due_date")
        billing = cleaned.get("billing_type")
        rate = cleaned.get("hourly_rate")

        if start and due and due < start:
            self.add_error("due_date", _("Due date can’t be earlier than start date."))

        # If hourly project, require a positive hourly rate
        if billing == Project.HOURLY:
            try:
                if rate is None or rate <= 0:
                    self.add_error("hourly_rate", _("Hourly projects require an hourly rate greater than 0."))
            except Exception:
                self.add_error("hourly_rate", _("Enter a valid hourly rate."))

        return cleaned
