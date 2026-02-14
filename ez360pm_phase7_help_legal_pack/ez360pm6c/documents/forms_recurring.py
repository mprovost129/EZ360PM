from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms
from django.forms import inlineformset_factory
from django.utils import timezone

from companies.services import get_active_company
from crm.models import Client

from .models import RecurringPlan, RecurringPlanLineItem, RecurringFrequency


class RecurringPlanForm(forms.ModelForm):
    class Meta:
        model = RecurringPlan
        fields = [
            "name",
            "client",
            "project",
            "frequency",
            "interval",
            "day_of_month",
            "next_run_date",
            "due_days",
            "auto_mark_sent",
            "auto_email",
            "email_to_override",
            "is_active",
            "notes",
        ]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "next_run_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args: Any, **kwargs: Any):
        request = kwargs.pop("request", None)
        super().__init__(*args, **kwargs)

        # Bootstrap widgets
        for name, field in self.fields.items():
            if isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")

        # Scope dropdowns by active company.
        if request is not None:
            company = get_active_company(request)
            if company is not None:
                self.fields["client"].queryset = Client.objects.filter(company=company, deleted_at__isnull=True).order_by(
                    "company_name", "last_name", "first_name"
                )
                # Project queryset is provided by Project FK in model; we filter it safely if present.
                try:
                    from projects.models import Project

                    self.fields["project"].queryset = Project.objects.filter(company=company, deleted_at__isnull=True).order_by("name")
                except Exception:
                    pass

        # Defaults
        if not self.instance.pk and not self.initial.get("next_run_date"):
            self.initial["next_run_date"] = timezone.localdate()

    def clean_day_of_month(self):
        dom = int(self.cleaned_data.get("day_of_month") or 1)
        if dom < 1:
            dom = 1
        if dom > 31:
            dom = 31
        return dom


class MoneyCentsField(forms.IntegerField):
    """Accepts dollars.cents input in UI and stores integer cents."""

    def prepare_value(self, value):
        if value is None:
            return ""
        try:
            return f"{int(value) / 100:.2f}"
        except Exception:
            return value

    def to_python(self, value):
        if value in (None, ""):
            return 0
        try:
            dec = Decimal(str(value).strip())
            return int(round(dec * 100))
        except Exception:
            return 0


class RecurringPlanLineItemForm(forms.ModelForm):
    unit_price_cents = MoneyCentsField(required=False, min_value=0)

    class Meta:
        model = RecurringPlanLineItem
        fields = ["sort_order", "name", "description", "qty", "unit_price_cents", "is_taxable"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 1}),
        }

    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if name in {"is_taxable", "DELETE"}:
                continue
            if isinstance(field.widget, (forms.CheckboxInput,)):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control form-control-sm")
        if "is_taxable" in self.fields:
            self.fields["is_taxable"].widget.attrs.setdefault("class", "form-check-input")


RecurringPlanLineItemFormSet = inlineformset_factory(
    RecurringPlan,
    RecurringPlanLineItem,
    form=RecurringPlanLineItemForm,
    extra=3,
    can_delete=True,
)
