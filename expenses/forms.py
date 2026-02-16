from __future__ import annotations

from django import forms
from django.conf import settings

from crm.models import Client
from payables.models import Vendor
from projects.models import Project

from .models import Expense, Merchant, ExpenseStatus


class MerchantForm(forms.ModelForm):
    class Meta:
        model = Merchant
        fields = ["name"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
        }


class ExpenseForm(forms.ModelForm):
    amount_dollars = forms.DecimalField(max_digits=12, decimal_places=2, required=True, min_value=0)
    tax_dollars = forms.DecimalField(max_digits=12, decimal_places=2, required=False, min_value=0)
    new_merchant_name = forms.CharField(max_length=160, required=False)
    receipt_s3_key = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Expense
        fields = [
            "merchant",
            "vendor",
            "date",
            "category",
            "client",
            "project",
            "description",
            "receipt",
            "receipt_s3_key",
            "status",
        ]
        widgets = {
            "merchant": forms.Select(attrs={"class": "form-select"}),
            "vendor": forms.Select(attrs={"class": "form-select"}),
            "date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "category": forms.TextInput(attrs={"class": "form-control"}),
            "client": forms.Select(attrs={"class": "form-select"}),
            "project": forms.Select(attrs={"class": "form-select"}),
            "description": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "receipt": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "status": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.company = company
        if company is not None:
            self.fields["merchant"].queryset = Merchant.objects.filter(company=company, is_deleted=False).order_by("name")
            self.fields["client"].queryset = Client.objects.filter(company=company, is_deleted=False).order_by("company_name", "last_name", "first_name")
            self.fields["project"].queryset = Project.objects.filter(company=company, is_deleted=False).order_by("name")
            self.fields["vendor"].queryset = Vendor.objects.filter(company=company, is_deleted=False).order_by("name")
        else:
            self.fields["merchant"].queryset = Merchant.objects.none()
            self.fields["client"].queryset = Client.objects.none()
            self.fields["project"].queryset = Project.objects.none()
            self.fields["vendor"].queryset = Vendor.objects.none()

        self.fields["new_merchant_name"].widget = forms.TextInput(attrs={"class": "form-control", "placeholder": "Or type a new merchant name"})

        if self.instance and self.instance.pk:
            self.fields["amount_dollars"].initial = (self.instance.amount_cents or 0) / 100
            self.fields["tax_dollars"].initial = (self.instance.tax_cents or 0) / 100

        if getattr(settings, "USE_S3", False) and getattr(settings, "S3_DIRECT_UPLOADS", False):
            # Direct upload flow: browser uploads to S3 and submits receipt_s3_key.
            self.fields["receipt"].required = False

    def clean(self):
        data = super().clean()
        merchant = data.get("merchant")
        new_name = (data.get("new_merchant_name") or "").strip()
        if not merchant and not new_name:
            self.add_error("merchant", "Select a merchant or enter a new merchant name.")
        return data

    def save(self, commit=True):
        inst: Expense = super().save(commit=False)
        amt = float(self.cleaned_data.get("amount_dollars") or 0)
        tax = float(self.cleaned_data.get("tax_dollars") or 0)
        inst.amount_cents = int(round(amt * 100))
        inst.tax_cents = int(round(tax * 100))
        inst.total_cents = inst.amount_cents + inst.tax_cents

        new_name = (self.cleaned_data.get("new_merchant_name") or "").strip()
        if not inst.merchant and new_name and self.company is not None:
            inst.merchant, _ = Merchant.objects.get_or_create(company=self.company, name=new_name)

        receipt_key = (self.cleaned_data.get("receipt_s3_key") or "").strip()
        if receipt_key and not self.cleaned_data.get("receipt"):
            inst.receipt.name = receipt_key

        if commit:
            inst.save()
        return inst
