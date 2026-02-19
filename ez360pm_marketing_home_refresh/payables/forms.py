from __future__ import annotations

from django import forms

from core.forms.money import MoneyCentsField
from accounting.models import Account, AccountType

from .models import Vendor, Bill, BillLineItem, BillPayment, RecurringBillPlan


class VendorForm(forms.ModelForm):
    class Meta:
        model = Vendor
        fields = [
            "name",
            "email",
            "phone",
            "address1",
            "address2",
            "city",
            "state",
            "postal_code",
            "country",
            "notes",
            "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email": forms.EmailInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "address1": forms.TextInput(attrs={"class": "form-control"}),
            "address2": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control"}),
            "postal_code": forms.TextInput(attrs={"class": "form-control"}),
            "country": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class BillForm(forms.ModelForm):
    # Store cents, accept dollars in UI
    tax_cents = MoneyCentsField(required=False, min_value=0, label="Tax (optional)")

    class Meta:
        model = Bill
        fields = [
            "vendor",
            "bill_number",
            "issue_date",
            "due_date",
            "tax_cents",
        ]
        widgets = {
            "vendor": forms.Select(attrs={"class": "form-select"}),
            "bill_number": forms.TextInput(attrs={"class": "form-control"}),
            "issue_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "due_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["vendor"].queryset = Vendor.objects.filter(company=company, is_active=True, deleted_at__isnull=True).order_by("name")

        self.fields["tax_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["tax_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["tax_cents"].widget.attrs.setdefault("step", "0.01")

        if self.instance and self.instance.pk:
            self.fields["tax_cents"].initial = int(self.instance.tax_cents or 0)


class BillLineItemForm(forms.ModelForm):
    unit_price_cents = MoneyCentsField(required=True, min_value=0, label="Unit price")

    class Meta:
        model = BillLineItem
        fields = ["description", "quantity", "expense_account", "unit_price_cents"]
        widgets = {
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "expense_account": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["expense_account"].queryset = Account.objects.filter(
                company=company, type=AccountType.EXPENSE, is_active=True, deleted_at__isnull=True
            ).order_by("code", "name")

        self.fields["unit_price_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["unit_price_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["unit_price_cents"].widget.attrs.setdefault("step", "0.01")

        if self.instance and self.instance.pk:
            self.fields["unit_price_cents"].initial = int(self.instance.unit_price_cents or 0)


class BillPaymentForm(forms.ModelForm):
    amount_cents = MoneyCentsField(required=True, min_value=1, label="Amount")

    class Meta:
        model = BillPayment
        fields = ["payment_date", "payment_account", "reference", "amount_cents"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "payment_account": forms.Select(attrs={"class": "form-select"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["payment_account"].queryset = Account.objects.filter(
                company=company, type=AccountType.ASSET, is_active=True, deleted_at__isnull=True
            ).order_by("code", "name")

        self.fields["amount_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["amount_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["amount_cents"].widget.attrs.setdefault("step", "0.01")

        if self.instance and self.instance.pk:
            self.fields["amount_cents"].initial = int(self.instance.amount_cents or 0)


class RecurringBillPlanForm(forms.ModelForm):
    amount_cents = MoneyCentsField(required=True, min_value=0, label="Amount")

    class Meta:
        model = RecurringBillPlan
        fields = ["vendor", "expense_account", "frequency", "next_run", "is_active", "auto_post", "amount_cents"]
        widgets = {
            "vendor": forms.Select(attrs={"class": "form-select"}),
            "expense_account": forms.Select(attrs={"class": "form-select"}),
            "frequency": forms.Select(attrs={"class": "form-select"}),
            "next_run": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "auto_post": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["vendor"].queryset = Vendor.objects.filter(company=company, is_active=True, deleted_at__isnull=True).order_by("name")
            self.fields["expense_account"].queryset = Account.objects.filter(
                company=company, type=AccountType.EXPENSE, is_active=True, deleted_at__isnull=True
            ).order_by("code", "name")

        self.fields["amount_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["amount_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["amount_cents"].widget.attrs.setdefault("step", "0.01")

        if self.instance and self.instance.pk:
            self.fields["amount_cents"].initial = int(self.instance.amount_cents or 0)
