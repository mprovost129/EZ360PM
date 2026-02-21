from __future__ import annotations

from django import forms

from core.forms.money import MoneyCentsField
from documents.models import Document, DocumentType

from .models import Payment, PaymentStatus


class PaymentForm(forms.ModelForm):
    # Store cents in model, accept dollars in UI
    amount_cents = MoneyCentsField(required=True, min_value=1, label="Amount")

    class Meta:
        model = Payment
        fields = ["invoice", "payment_date", "method", "notes", "status", "amount_cents"]
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
            self.fields["invoice"].queryset = Document.objects.filter(company=company, doc_type=DocumentType.INVOICE).order_by(
                "-updated_at"
            )

        # Ensure consistent widget attrs
        self.fields["amount_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["amount_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["amount_cents"].widget.attrs.setdefault("step", "0.01")

        if self.instance and self.instance.pk:
            self.fields["amount_cents"].initial = int(self.instance.amount_cents or 0)

    def clean(self):
        data = super().clean()
        inv = data.get("invoice")
        if inv and inv.doc_type != DocumentType.INVOICE:
            self.add_error("invoice", "Selected document is not an invoice.")
        return data


class PaymentRefundForm(forms.Form):
    """Refund form used on Payment edit screen."""

    amount_cents = MoneyCentsField(required=True, min_value=1, label="Refund amount")
    memo = forms.CharField(
        required=False,
        max_length=200,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional memo"}),
    )

    def __init__(self, *args, payment: Payment, **kwargs):
        super().__init__(*args, **kwargs)
        self.payment = payment

        self.fields["amount_cents"].widget.attrs.setdefault("class", "form-control")
        self.fields["amount_cents"].widget.attrs.setdefault("placeholder", "$0.00")
        self.fields["amount_cents"].widget.attrs.setdefault("step", "0.01")

        refundable = self.refundable_cents
        if refundable > 0 and not self.is_bound:
            self.fields["amount_cents"].initial = refundable

    @property
    def refundable_cents(self) -> int:
        paid = int(self.payment.amount_cents or 0)
        refunded = int(getattr(self.payment, "refunded_cents", 0) or 0)
        return max(0, paid - refunded)

    def clean_amount_cents(self):
        cents = int(self.cleaned_data["amount_cents"])
        refundable = self.refundable_cents

        if refundable <= 0:
            raise forms.ValidationError("This payment is not refundable.")
        if cents > refundable:
            raise forms.ValidationError("Refund amount exceeds refundable remainder.")
        if self.payment.status not in {PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED}:
            raise forms.ValidationError("Only succeeded/refunded payments can be refunded.")

        return cents
