# estimates/forms.py
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django import forms
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory, BaseInlineFormSet
from django.utils.translation import gettext_lazy as _

from clients.models import Client
from company.models import Company
from projects.models import Project

from .models import Estimate, EstimateItem


# -------------------------------------------------------------------
# Estimate
# -------------------------------------------------------------------

class EstimateForm(forms.ModelForm):
    """
    Pass `company=` to scope client/project selects and validate per-company
    estimate number uniqueness.
    """

    class Meta:
        model = Estimate
        fields = [
            "number",
            "client",
            "project",
            "status",
            "issue_date",
            "valid_until",
            "tax",
            "notes",
            "is_template",
        ]
        widgets = {
            "number": forms.TextInput(attrs={
                "class": "form-control",
                "autocomplete": "off",
                "placeholder": "EST-2041",
            }),
            "client": forms.Select(attrs={"class": "form-select"}),
            "project": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "issue_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "valid_until": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "tax": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "is_template": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        self._company: Optional[Company] = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)

        # Scope selects by company
        if self._company:
            self.fields["client"].queryset = ( # type: ignore
                Client.objects.filter(company=self._company).order_by("org", "last_name")  # type: ignore
            )
            self.fields["project"].queryset = ( # type: ignore
                Project.objects.filter(company=self._company).order_by("-created_at")  # type: ignore
            )

        # Nice empty labels
        self.fields["client"].empty_label = _("— Select client —")  # type: ignore
        self.fields["project"].empty_label = _("— (optional) Select project —")  # type: ignore

        # Defaults
        if self.instance.pk is None and not self.initial.get("tax"):
            self.initial["tax"] = Decimal("0.00")

    def clean_number(self) -> str:
        number = (self.cleaned_data.get("number") or "").strip()
        if number and self._company:
            qs = Estimate.objects.filter(company=self._company, number__iexact=number)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise ValidationError(
                    _("An estimate with this number already exists in your company.")
                )
        return number

    def clean(self):
        data = super().clean()
        issue = data.get("issue_date")
        valid_until = data.get("valid_until")
        project: Optional[Project] = data.get("project")
        client: Optional[Client] = data.get("client")
        tax = data.get("tax")

        if issue and valid_until and valid_until < issue:
            self.add_error("valid_until", _("Valid until date cannot be before the issue date."))

        # Project ↔ client consistency
        if project and client is None:
            data["client"] = project.client
        elif project and client and project.client_id != client.id:  # type: ignore
            self.add_error("project", _("Selected project belongs to a different client."))

        # Tax normalization
        if tax is None:
            data["tax"] = Decimal("0.00")
        elif tax < 0:
            self.add_error("tax", _("Tax cannot be negative."))

        return data


# -------------------------------------------------------------------
# Estimate Items
# -------------------------------------------------------------------

class EstimateItemForm(forms.ModelForm):
    class Meta:
        model = EstimateItem
        fields = ["description", "qty", "unit_price"]
        widgets = {
            "description": forms.Textarea(
                attrs={"class": "form-control", "rows": 2, "placeholder": _("Describe the work/item")}
            ),
            "qty": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
            "unit_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
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


class BaseEstimateItemFormSet(BaseInlineFormSet):
    """
    Ensures at least one non-deleted line item is present and
    refreshes parent Estimate totals after save().

    NOTE: Totals are updated using Estimate.recalc_totals() which assumes
    `tax` is an absolute amount stored on the Estimate.
    """

    def clean(self):
        super().clean()
        # Require at least one non-deleted row when the estimate is not a template
        non_deleted = 0
        for f in self.forms:
            if not hasattr(f, "cleaned_data"):
                continue
            cd = f.cleaned_data
            if cd and not cd.get("DELETE", False):
                # Consider a row valid if description present or qty/price > 0
                has_content = any([
                    bool(cd.get("description")),
                    (cd.get("qty") or Decimal("0")) > 0,
                    (cd.get("unit_price") or Decimal("0")) > 0,
                ])
                if has_content:
                    non_deleted += 1

        # If the parent form says it's a template, allow 0 items.
        is_template = False
        try:
            is_template = bool(self.instance.is_template)
        except Exception:
            pass

        if non_deleted == 0 and not is_template:
            raise ValidationError(_("Add at least one line item."))

    def save(self, commit=True):
        objs = super().save(commit=commit)
        # Recalc parent totals after items are saved
        parent = self.instance
        # If parent hasn’t been saved yet, nothing to recalc
        if parent and parent.pk:
            parent.recalc_totals()
            if commit:
                parent.save(update_fields=["subtotal", "total"])
        return objs


EstimateItemFormSet = inlineformset_factory(
    Estimate,
    EstimateItem,
    form=EstimateItemForm,
    formset=BaseEstimateItemFormSet,
    extra=3,
    can_delete=True,
)
# If you ever need to enforce at least one form at the widget level:
# min_num=1, validate_min=True


# -------------------------------------------------------------------
# Estimate → Project wizard
# -------------------------------------------------------------------

class ConvertEstimateToProjectForm(forms.Form):
    MODE_NEW = "new"
    MODE_ATTACH = "attach"

    mode = forms.ChoiceField(
        choices=[(MODE_NEW, _("Create new project")), (MODE_ATTACH, _("Attach to existing project"))],
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
        initial=MODE_NEW,
        label=_("Mode"),
    )

    existing_project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        required=False,
        empty_label=_("— Select a project —"),
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Existing project"),
    )

    new_number = forms.CharField(
        required=False,
        label=_("Project #"),
        widget=forms.TextInput(attrs={"class": "form-control", "autocomplete": "off"}),
    )
    new_name = forms.CharField(
        required=False,
        label=_("Project name"),
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )
    new_billing_type = forms.ChoiceField(
        choices=[(Project.HOURLY, _("Hourly")), (Project.FLAT, _("Flat rate"))],
        required=False,
        initial=Project.HOURLY,
        widget=forms.Select(attrs={"class": "form-select"}),
        label=_("Billing type"),
    )
    new_estimated_hours = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=9,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.25", "min": "0"}),
        label=_("Estimated hours"),
    )
    new_budget = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=12,
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
        label=_("Budget"),
    )
    new_start_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label=_("Start date"),
    )
    new_due_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}),
        label=_("Due date"),
    )

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        client = kwargs.pop("client", None)
        super().__init__(*args, **kwargs)
        qs = Project.objects.none()
        if company:
            qs = Project.objects.filter(company=company).order_by("-created_at")
            if client:
                qs = qs.filter(client=client)
        self.fields["existing_project"].queryset = qs  # type: ignore

    def clean(self):
        data = super().clean()
        mode = data.get("mode")
        if mode == self.MODE_ATTACH:
            if not data.get("existing_project"):
                self.add_error("existing_project", _("Choose a project to attach to."))
        else:
            if not data.get("new_name"):
                self.add_error("new_name", _("Project name is required."))
            if not data.get("new_billing_type"):
                self.add_error("new_billing_type", _("Select a billing type."))
            start = data.get("new_start_date")
            due = data.get("new_due_date")
            if start and due and due < start:
                self.add_error("new_due_date", _("Due date cannot be before start date."))
        return data
