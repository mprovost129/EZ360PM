# invoices/forms.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.utils.translation import gettext_lazy as _

from clients.models import Client
from company.models import Company
from projects.models import Project

from .models import Invoice, InvoiceItem, RecurringPlan


class InvoiceForm(forms.ModelForm):
    """
    Pass `company=` to scope client/project selects and validate per-company
    invoice number uniqueness + ownership of related objects.
    """
    def __init__(self, *args, **kwargs):
        self._company: Optional[Company] = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)

        if self._company:
            self.fields["client"].queryset = Client.objects.filter(company=self._company).order_by("org", "last_name") # type: ignore
            self.fields["project"].queryset = Project.objects.filter(company=self._company).order_by("-created_at") # type: ignore

        self.fields["client"].empty_label = "— Select client —"            # type: ignore[attr-defined]
        self.fields["project"].empty_label = "— (optional) Select project —"  # type: ignore[attr-defined]

        # Nice default for tax on new invoices
        if self.instance.pk is None and not self.initial.get("tax"):
            self.initial["tax"] = Decimal("0.00")

    class Meta:
        model = Invoice
        fields = ["project", "client", "number", "status", "issue_date", "due_date", "notes", "tax"]
        widgets = {
            "project":    forms.Select(attrs={"class": "form-select"}),
            "client":     forms.Select(attrs={"class": "form-select"}),
            "number":     forms.TextInput(attrs={"class": "form-control", "autocomplete": "off", "placeholder": "INV-1008"}),
            "status":     forms.Select(attrs={"class": "form-select"}),
            "issue_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "due_date":   forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "notes":      forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "tax":        forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "inputmode": "decimal"}),
        }

    # ----- Field cleans -----------------------------------------------------

    def clean_number(self):
        number = (self.cleaned_data.get("number") or "").strip()
        if number and self._company:
            qs = Invoice.objects.filter(company=self._company, number__iexact=number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(_("An invoice with this number already exists in your company."))
        return number

    def clean_client(self):
        client = self.cleaned_data.get("client")
        if self._company and client and getattr(client, "company_id", None) != getattr(self._company, "id", None):
            raise ValidationError(_("Selected client does not belong to your company."))
        return client

    def clean_project(self):
        project = self.cleaned_data.get("project")
        if self._company and project and getattr(project, "company_id", None) != getattr(self._company, "id", None):
            raise ValidationError(_("Selected project does not belong to your company."))
        return project

    # ----- Form-level clean -------------------------------------------------

    def clean(self):
        data = super().clean()
        issue = data.get("issue_date")
        due = data.get("due_date")
        project: Optional[Project] = data.get("project")
        client: Optional[Client] = data.get("client")
        tax = data.get("tax")

        if issue and due and due < issue:
            self.add_error("due_date", _("Due date cannot be before the issue date."))

        # Auto-fill client from project if missing; otherwise ensure they match
        if project and client is None:
            data["client"] = project.client
        elif project and client and project.client_id != client.id: # type: ignore
            self.add_error("project", _("Selected project belongs to a different client."))

        # Normalize tax
        if tax is None:
            data["tax"] = Decimal("0.00")
        elif tax < 0:
            self.add_error("tax", _("Tax cannot be negative."))

        return data


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ["description", "qty", "unit_price"]
        widgets = {
            "description": forms.TextInput(attrs={"class": "form-control", "placeholder": _("Describe the work/item")}),
            "qty":         forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01", "inputmode": "decimal"}),
            "unit_price":  forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0", "inputmode": "decimal"}),
        }

    def clean_qty(self):
        qty = self.cleaned_data.get("qty")
        if qty is None or qty <= 0:
            raise forms.ValidationError(_("Quantity must be greater than 0."))
        return qty

    def clean_unit_price(self):
        price = self.cleaned_data.get("unit_price")
        if price is None or price < 0:
            raise forms.ValidationError(_("Unit price cannot be negative."))
        return price


# Require at least 1 line item; adjust extra/min_num to your taste
InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    extra=2,
    can_delete=True,
    min_num=1,
    validate_min=True,
)


class TimeToInvoiceForm(forms.Form):
    ROUNDING_CHOICES = [
        ("none", "No rounding"),
        ("0.05", "Nearest 0.05 h (3 min)"),
        ("0.1", "Nearest 0.1 h (6 min)"),
        ("0.25", "Nearest 0.25 h (15 min)"),
        ("0.5", "Nearest 0.5 h (30 min)"),
        ("1", "Nearest 1.0 h"),
    ]
    GROUPING_CHOICES = [
        ("project", "Single line (all time)"),
        ("day", "One line per day"),
        ("user", "One line per user"),
        ("entry", "One line per entry"),
    ]
    EXPENSE_GROUPING_CHOICES = [
        ("all", "Single line: all expenses (summed)"),
        ("category", "Group by category"),
        ("vendor", "Group by vendor"),
        ("expense", "One line per expense"),
    ]

    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    rounding = forms.ChoiceField(choices=ROUNDING_CHOICES, initial="0.25",
                                 widget=forms.Select(attrs={"class": "form-select"}))
    group_by = forms.ChoiceField(choices=GROUPING_CHOICES, initial="day",
                                 widget=forms.Select(attrs={"class": "form-select"}))
    override_rate = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=10,
        help_text=_("Leave blank to use project hourly rate."),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        help_text=_("Shown on invoice lines (prefix)."),
    )
    include_expenses = forms.BooleanField(required=False, initial=True, label=_("Include billable expenses"),
                                          widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    include_only_approved = forms.BooleanField(required=False, initial=True, label=_("Only include approved time"),
                                               widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    expense_group_by = forms.ChoiceField(choices=EXPENSE_GROUPING_CHOICES, initial="category", required=False,
                                         widget=forms.Select(attrs={"class": "form-select"}))
    expense_markup_override = forms.DecimalField(
        required=False, min_value=0, decimal_places=2, max_digits=5,
        help_text=_("Optional % markup to override per-expense markup (e.g., 10.00 for 10%)."),
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
    )
    expense_label_prefix = forms.CharField(
        required=False, max_length=80,
        help_text=_("Optional label prefix, e.g., 'Reimbursable expense'."),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def clean(self):
        data = super().clean()
        start = data.get("start")
        end = data.get("end")
        if start and end and end < start:
            self.add_error("end", _("End date cannot be before start date."))

        if not data.get("include_expenses"):
            # Null out expense-only fields if expenses are excluded
            data["expense_group_by"] = None
            data["expense_markup_override"] = None
            data["expense_label_prefix"] = ""
        return data


# -------------------------------------------------------------------
# Recurring Plans
# -------------------------------------------------------------------

class RecurringPlanForm(forms.ModelForm):
    """
    Pass `company=` to scope selects. Validates:
    - dates order (start ≤ next_run ≤ end if provided),
    - project/client belong to company,
    - template invoice belongs to company and (optionally) matches client.
    """
    def __init__(self, *args, **kwargs):
        self._company: Optional[Company] = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        if self._company:
            self.fields["client"].queryset = Client.objects.filter(company=self._company).order_by("org", "last_name") # type: ignore
            self.fields["project"].queryset = Project.objects.filter(company=self._company).order_by("-created_at") # type: ignore
            self.fields["template_invoice"].queryset = Invoice.objects.filter(company=self._company).order_by("-issue_date") # type: ignore

        # Optional empty labels
        self.fields["project"].empty_label = "— (optional) Select project —"           # type: ignore[attr-defined]
        self.fields["template_invoice"].empty_label = "— (optional) Select template —"  # type: ignore[attr-defined]

    class Meta:
        model = RecurringPlan
        fields = [
            "title", "client", "project", "template_invoice", "frequency",
            "start_date", "next_run_date", "end_date", "due_days",
            "status", "auto_email", "max_occurrences",
        ]
        widgets = {
            "title":            forms.TextInput(attrs={"class": "form-control"}),
            "client":           forms.Select(attrs={"class": "form-select"}),
            "project":          forms.Select(attrs={"class": "form-select"}),
            "template_invoice": forms.Select(attrs={"class": "form-select"}),
            "frequency":        forms.Select(attrs={"class": "form-select"}),
            "start_date":       forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "next_run_date":    forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "end_date":         forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "due_days":         forms.NumberInput(attrs={"class": "form-control", "min": "0", "step": "1"}),
            "status":           forms.Select(attrs={"class": "form-select"}),
            "auto_email":       forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "max_occurrences":  forms.NumberInput(attrs={"class": "form-control", "min": "1", "step": "1"}),
        }

    # ----- Form-level clean -------------------------------------------------

    def clean(self):
        data = super().clean()
        client: Optional[Client] = data.get("client")
        project: Optional[Project] = data.get("project")
        tmpl: Optional[Invoice] = data.get("template_invoice")
        start = data.get("start_date")
        next_run = data.get("next_run_date")
        end = data.get("end_date")

        # Dates order: start ≤ next_run ≤ end (when provided)
        if start and next_run and next_run < start:
            self.add_error("next_run_date", _("Next run date cannot be before the start date."))
        if start and end and end < start:
            self.add_error("end_date", _("End date cannot be before the start date."))
        if next_run and end and end < next_run:
            self.add_error("end_date", _("End date cannot be before the next run date."))

        # Company scoping + client consistency
        if self._company:
            if client and getattr(client, "company_id", None) != getattr(self._company, "id", None):
                self.add_error("client", _("Selected client does not belong to your company."))
            if project and getattr(project, "company_id", None) != getattr(self._company, "id", None):
                self.add_error("project", _("Selected project does not belong to your company."))
            if tmpl and getattr(tmpl, "company_id", None) != getattr(self._company, "id", None):
                self.add_error("template_invoice", _("Selected template invoice does not belong to your company."))

        # Ensure project belongs to the same client (if both set)
        if project and client and getattr(project, "client_id", None) != getattr(client, "id", None):
            self.add_error("project", _("Selected project belongs to a different client."))

        # Optional: ensure template invoice matches selected client
        if tmpl and client and getattr(tmpl, "client_id", None) != getattr(client, "id", None):
            self.add_error("template_invoice", _("Template invoice belongs to a different client."))

        return data
