# expenses/forms.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from projects.models import Project
from .models import Expense


class ExpenseForm(forms.ModelForm):
    """
    Expense create/edit form scoped to a company.
    Pass `company=<Company>` when instantiating to filter the project list
    and validate project ownership.
    """

    class Meta:
        model = Expense
        fields = [
            "date", "vendor", "category", "description",
            "project", "amount",
            "is_billable", "billable_markup_pct", "billable_note",
        ]
        labels = {
            "vendor": _("Vendor"),
            "category": _("Category"),
            "description": _("Description"),
            "project": _("Project (optional)"),
            "amount": _("Amount"),
            "is_billable": _("Billable to client"),
            "billable_markup_pct": _("Markup %"),
            "billable_note": _("Billable note (optional)"),
            "date": _("Date"),
        }
        help_texts = {
            "billable_markup_pct": _("Enter as a percentage, e.g. 10.00 for 10%"),
        }
        widgets = {
            "date":     forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "vendor":   forms.TextInput(attrs={"class": "form-control", "placeholder": _("e.g., Home Depot")}),
            "category": forms.TextInput(attrs={"class": "form-control", "placeholder": _("e.g., Materials, Fuel")}),  # swap to Select when you add choices
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": _("What is this expense for?")}),
            "project":  forms.Select(attrs={"class": "form-select"}),
            "amount":   forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "inputmode": "decimal"}),
            "is_billable": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "billable_markup_pct": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "inputmode": "decimal"}),
            "billable_note": forms.TextInput(attrs={"class": "form-control", "placeholder": _("Optional note for the client")}),
        }
        error_messages = {
            "amount": {
                "min_value": _("Amount must be zero or greater."),
            }
        }

    def __init__(self, *args, **kwargs):
        # Expect a company to scope projects and validate ownership.
        self.company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)

        # Default date to today for new objects (if not already set by instance/POST)
        if not self.instance.pk and not self.initial.get("date") and not self.data.get(self.add_prefix("date")):
            self.initial["date"] = timezone.localdate()

        # Project queryset scoped to company (if provided)
        if self.company:
            self.fields["project"].queryset = ( # type: ignore
                Project.objects.filter(company=self.company).order_by("-created_at")  # type: ignore[attr-defined]
            )
        self.fields["project"].required = False
        self.fields["project"].empty_label = _("— No project —") # type: ignore

        # Nice default for markup when billable is toggled on
        if not self.instance.pk and not self.data:
            self.initial.setdefault("billable_markup_pct", "0.00")

    # ---- Field-level cleans ------------------------------------------------

    def clean_project(self):
        project = self.cleaned_data.get("project")
        if project and self.company and getattr(project, "company_id", None) != getattr(self.company, "id", None):
            raise ValidationError(_("Selected project does not belong to your company."))
        return project

    def clean_billable_markup_pct(self):
        """
        Normalize markup to a non-negative Decimal with two places (string inputs, commas, etc).
        """
        raw = self.data.get(self.add_prefix("billable_markup_pct"), self.cleaned_data.get("billable_markup_pct"))
        if raw in (None, "",):
            return Decimal("0.00")
        try:
            val = Decimal(str(raw)).quantize(Decimal("0.01"))
        except (InvalidOperation, TypeError):
            raise ValidationError(_("Enter a valid percentage (e.g., 10.00)."))
        if val < 0:
            raise ValidationError(_("Markup must be zero or greater."))
        # Soft upper bound to prevent accidents; model also has a validator/constraint
        if val > Decimal("999.99"):
            raise ValidationError(_("Markup seems too large. Please enter a value under 1000%."))
        return val

    # ---- Form-level clean --------------------------------------------------

    def clean(self):
        cleaned = super().clean()

        is_billable = cleaned.get("is_billable") is True
        markup = cleaned.get("billable_markup_pct") or Decimal("0.00")
        note = (cleaned.get("billable_note") or "").strip()
        amount = cleaned.get("amount") or Decimal("0.00")

        # Enforce non-negative amounts (model has validator/constraint; this is a friendly check)
        if amount < 0:
            self.add_error("amount", _("Amount must be zero or greater."))

        # If not billable, force markup to 0 and allow empty note
        if not is_billable:
            cleaned["billable_markup_pct"] = Decimal("0.00")
            cleaned["billable_note"] = note  # leave as-is (often empty)
        else:
            # If billable but markup omitted, keep 0.00; note is optional
            cleaned["billable_note"] = note

        return cleaned
