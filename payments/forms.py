from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django import forms

from documents.models import Document, DocumentType

from .models import Payment, PaymentMethod, PaymentStatus


class PaymentForm(forms.ModelForm):
    amount_dollars = forms.DecimalField(max_digits=12, decimal_places=2, required=True, min_value=0)

    class Meta:
        model = Payment
        fields = ["invoice", "payment_date", "method", "notes", "status"]
        widgets = {
            "payment_date": forms.DateInput(attrs={"type": "date", "class": "form-control"}),
            "method": forms.Select(attrs={"class": "form-select"}),
            "invoice": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "notes": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
        }

    def __init__(self, *args, company=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["invoice"].queryset = Document.objects.none()
        if company is not None:
            self.fields["invoice"].queryset = (
                Document.objects.filter(company=company, doc_type=DocumentType.INVOICE)
                .order_by("-updated_at")
            )
        for name in self.fields:
            if name not in {"payment_date", "method", "invoice", "status", "notes"}:
                self.fields[name].widget.attrs.setdefault("class", "form-control")

        if self.instance and self.instance.pk:
            self.fields["amount_dollars"].initial = (Decimal(int(self.instance.amount_cents or 0)) / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

        self.fields["amount_dollars"].widget.attrs.setdefault("class", "form-control")
        self.fields["amount_dollars"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["amount_dollars"].widget.attrs.setdefault("step", "0.01")

    def clean(self):
        data = super().clean()
        inv = data.get("invoice")
        if inv and inv.doc_type != DocumentType.INVOICE:
            self.add_error("invoice", "Selected document is not an invoice.")
        return data

    def save(self, commit=True):
        inst: Payment = super().save(commit=False)
        dollars = self.cleaned_data.get("amount_dollars")
        amt = Decimal(dollars or 0).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        inst.amount_cents = int((amt * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        if commit:
            inst.save()
        return inst


class ApplyClientCreditForm(forms.Form):
    amount_dollars = forms.DecimalField(max_digits=12, decimal_places=2, required=True, min_value=0.01)
    memo = forms.CharField(max_length=240, required=False)

    def clean_amount_dollars(self):
        val = self.cleaned_data["amount_dollars"]
        return val


class PaymentRefundForm(forms.Form):
    amount_dollars = forms.DecimalField(max_digits=12, decimal_places=2, required=True, min_value=0.01)
    memo = forms.CharField(required=False, max_length=240)

    def __init__(self, *args, payment: Payment, **kwargs):
        self.payment = payment
        super().__init__(*args, **kwargs)

        self.fields["amount_dollars"].widget.attrs.update({"class": "form-control"})
        self.fields["memo"].widget.attrs.update({"class": "form-control", "placeholder": "Reason / note (optional)"})

    def clean(self):
        cleaned = super().clean()
        amt = cleaned.get("amount_dollars")
        if amt is None:
            return cleaned
        cents = int((Decimal(amt).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP) * Decimal('100')).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
        refundable = max(0, int(self.payment.amount_cents or 0) - int(self.payment.refunded_cents or 0))
        if cents <= 0:
            raise forms.ValidationError("Refund amount must be greater than $0.00.")
        if cents > refundable:
            raise forms.ValidationError("Refund amount exceeds refundable balance.")
        cleaned["amount_cents"] = cents
        return cleaned
