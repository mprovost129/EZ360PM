from __future__ import annotations

from django import forms

from .models import BankReconciliationPeriod, BankRule


class BankRuleForm(forms.ModelForm):
    class Meta:
        model = BankRule
        fields = [
            "is_active",
            "priority",
            "match_field",
            "match_type",
            "match_text",
            "min_amount_cents",
            "max_amount_cents",
            "merchant_name",
            "expense_category",
            "action",
        ]
        widgets = {
            "match_text": forms.TextInput(attrs={"class": "form-control"}),
            "merchant_name": forms.TextInput(attrs={"class": "form-control"}),
            "expense_category": forms.TextInput(attrs={"class": "form-control"}),
            "min_amount_cents": forms.NumberInput(attrs={"class": "form-control"}),
            "max_amount_cents": forms.NumberInput(attrs={"class": "form-control"}),
            "priority": forms.NumberInput(attrs={"class": "form-control"}),
        }


class BankReconciliationPeriodForm(forms.ModelForm):
    class Meta:
        model = BankReconciliationPeriod
        fields = ["start_date", "end_date", "notes"]
        widgets = {
            "start_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "end_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after the start date.")
        return cleaned
