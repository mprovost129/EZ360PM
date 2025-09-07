# payments/forms.py
from __future__ import annotations

from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from payments.models import Payment


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "received_at", "method"]
        widgets = {
            "amount": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "received_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "method": forms.TextInput(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure HTML5 datetime-local parses cleanly (YYYY-MM-DDTHH:MM)
        if "received_at" in self.fields:
            self.fields["received_at"].input_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"] # type: ignore

    def clean_amount(self):
        amt = self.cleaned_data.get("amount")
        if amt is None or amt <= 0:
            raise ValidationError(_("Amount must be greater than 0."))
        return amt

    def clean_received_at(self):
        dt = self.cleaned_data.get("received_at")
        if dt and timezone.is_naive(dt):
            # Coerce to current time zone
            dt = timezone.make_aware(dt, timezone.get_current_timezone())
        return dt


# -------------------------------------------------------------------
# Refunds
# -------------------------------------------------------------------

class RefundForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Refund amount",
        widget=forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0.01"}),
    )
    use_stripe = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Issue a Stripe refund to the card (requires a Stripe payment).",
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
    )
    payment_intent = forms.ChoiceField(
        required=False,
        help_text="Which Stripe payment to refund?",
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        invoice = kwargs.pop("invoice", None)
        super().__init__(*args, **kwargs)

        pis: list[tuple[str, str]] = []
        if invoice:
            qs = (
                invoice.payments
                .filter(method__iexact="stripe")
                .exclude(external_id="")
                .order_by("-received_at")
            )
            for p in qs:
                # external_id expected to be Stripe PaymentIntent id (e.g., pi_...)
                label = f"{p.external_id} — ${p.amount:.2f} on {timezone.localtime(p.received_at).strftime('%Y-%m-%d %H:%M')}"
                pis.append((p.external_id, label))

        if pis:
            self.fields["payment_intent"].choices = pis
        else:
            # No Stripe payments to refund; hide related fields
            self.fields.pop("payment_intent", None)
            self.fields.pop("use_stripe", None)
