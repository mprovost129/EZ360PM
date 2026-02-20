from __future__ import annotations

from django import forms
from django.conf import settings

from core.forms.money import MoneyCentsField
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
    # Store cents in the model, but accept dollars in the UI.
    amount_cents = MoneyCentsField(required=True, min_value=0, label="Amount")
    tax_cents = MoneyCentsField(required=False, min_value=0, label="Tax (optional)")

    new_merchant_name = forms.CharField(max_length=160, required=False)
    receipt_s3_key = forms.CharField(required=False, widget=forms.HiddenInput())

    class Meta:
        model = Expense
        fields = [
            "merchant",
            "new_merchant_name",
            "vendor",
            "date",
            "category",
            "client",
            "project",
            "description",
            "amount_cents",
            "tax_cents",
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

        # Ensure widgets are consistent
        self.fields["amount_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["amount_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["amount_cents"].widget.attrs.setdefault("step", "0.01")

        self.fields["tax_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["tax_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["tax_cents"].widget.attrs.setdefault("step", "0.01")

        if company is not None:
            self.fields["merchant"].queryset = Merchant.objects.filter(company=company, is_deleted=False).order_by("name")
            self.fields["client"].queryset = Client.objects.filter(company=company, is_deleted=False).order_by(
                "company_name", "last_name", "first_name"
            )
            self.fields["project"].queryset = Project.objects.filter(company=company, is_deleted=False).order_by("name")
            self.fields["vendor"].queryset = Vendor.objects.filter(company=company, is_deleted=False).order_by("name")
        else:
            self.fields["merchant"].queryset = Merchant.objects.none()
            self.fields["client"].queryset = Client.objects.none()
            self.fields["project"].queryset = Project.objects.none()
            self.fields["vendor"].queryset = Vendor.objects.none()

        self.fields["new_merchant_name"].widget = forms.TextInput(
            attrs={"class": "form-control", "placeholder": "Or type a new merchant name"}
        )

        if self.instance and self.instance.pk:
            self.fields["amount_cents"].initial = int(self.instance.amount_cents or 0)
            self.fields["tax_cents"].initial = int(self.instance.tax_cents or 0)

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

        merchant = self.cleaned_data.get("merchant")
        new_name = (self.cleaned_data.get("new_merchant_name") or "").strip()
        if not merchant and new_name:
            merchant, _ = Merchant.objects.get_or_create(company=self.company, name=new_name, defaults={"is_deleted": False})
            inst.merchant = merchant

        if commit:
            inst.save()
            self.save_m2m()
        return inst
