from __future__ import annotations

from django import forms

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
    tax_dollars = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=12,
        label="Tax (optional)",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    class Meta:
        model = Bill
        fields = [
            "vendor",
            "bill_number",
            "issue_date",
            "due_date",
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

        # seed tax_dollars from instance
        inst: Bill | None = kwargs.get("instance")
        if inst is not None:
            self.fields["tax_dollars"].initial = (inst.tax_cents or 0) / 100

    def clean(self):
        cleaned = super().clean()
        tax = cleaned.get("tax_dollars")
        if tax is None:
            return cleaned
        try:
            cents = int(round(float(tax) * 100))
        except Exception:
            cents = 0
        cleaned["tax_cents"] = max(cents, 0)
        return cleaned

    def save(self, commit=True):
        obj: Bill = super().save(commit=False)
        tax_cents = int(self.cleaned_data.get("tax_cents") or 0)
        obj.tax_cents = tax_cents
        if commit:
            obj.save()
        return obj


class BillLineItemForm(forms.ModelForm):
    unit_price_dollars = forms.DecimalField(
        required=True,
        min_value=0,
        decimal_places=2,
        max_digits=12,
        label="Unit price",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    class Meta:
        model = BillLineItem
        fields = ["description", "quantity", "expense_account"]
        widgets = {
            "description": forms.TextInput(attrs={"class": "form-control"}),
            "quantity": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "expense_account": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["expense_account"].queryset = Account.objects.filter(company=company, type=AccountType.EXPENSE, is_active=True, deleted_at__isnull=True).order_by("code", "name")

        inst: BillLineItem | None = kwargs.get("instance")
        if inst is not None:
            self.fields["unit_price_dollars"].initial = (inst.unit_price_cents or 0) / 100

    def clean(self):
        cleaned = super().clean()
        price = cleaned.get("unit_price_dollars")
        try:
            cents = int(round(float(price) * 100))
        except Exception:
            cents = 0
        cleaned["unit_price_cents"] = max(cents, 0)
        return cleaned

    def save(self, commit=True):
        obj: BillLineItem = super().save(commit=False)
        obj.unit_price_cents = int(self.cleaned_data.get("unit_price_cents") or 0)
        if commit:
            obj.save()
        return obj


class BillPaymentForm(forms.ModelForm):
    amount_dollars = forms.DecimalField(
        required=True,
        min_value=0.01,
        decimal_places=2,
        max_digits=12,
        label="Amount",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    class Meta:
        model = BillPayment
        fields = ["payment_date", "payment_account", "reference"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "payment_account": forms.Select(attrs={"class": "form-select"}),
            "reference": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        if company is not None:
            self.fields["payment_account"].queryset = Account.objects.filter(company=company, type=AccountType.ASSET, is_active=True, deleted_at__isnull=True).order_by("code", "name")

        inst: BillPayment | None = kwargs.get("instance")
        if inst is not None:
            self.fields["amount_dollars"].initial = (inst.amount_cents or 0) / 100

    def clean(self):
        cleaned = super().clean()
        amt = cleaned.get("amount_dollars")
        try:
            cents = int(round(float(amt) * 100))
        except Exception:
            cents = 0
        cleaned["amount_cents"] = max(cents, 0)
        return cleaned

    def save(self, commit=True):
        obj: BillPayment = super().save(commit=False)
        obj.amount_cents = int(self.cleaned_data.get("amount_cents") or 0)
        if commit:
            obj.save()
        return obj



class RecurringBillPlanForm(forms.ModelForm):
    amount_dollars = forms.DecimalField(
        required=True,
        min_value=0,
        decimal_places=2,
        max_digits=12,
        label="Amount",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
    )

    class Meta:
        model = RecurringBillPlan
        fields = ["vendor", "expense_account", "frequency", "next_run", "is_active", "auto_post"]
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
            self.fields["expense_account"].queryset = Account.objects.filter(company=company, type=AccountType.EXPENSE, is_active=True, deleted_at__isnull=True).order_by("code", "name")

        inst: RecurringBillPlan | None = kwargs.get("instance")
        if inst is not None:
            self.fields["amount_dollars"].initial = (inst.amount_cents or 0) / 100

    def clean(self):
        cleaned = super().clean()
        amt = cleaned.get("amount_dollars")
        try:
            cents = int(round(float(amt) * 100)) if amt is not None else 0
        except Exception:
            cents = 0
        cleaned["amount_cents"] = max(cents, 0)
        return cleaned

    def save(self, commit=True):
        obj: RecurringBillPlan = super().save(commit=False)
        obj.amount_cents = int(self.cleaned_data.get("amount_cents") or 0)
        if commit:
            obj.save()
        return obj
