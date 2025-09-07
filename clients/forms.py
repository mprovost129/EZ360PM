# clients/forms.py
from __future__ import annotations

from django import forms
from .models import Client


class BootstrapFormMixin:
    """Apply Bootstrap form-control classes automatically."""
    def _init_bootstrap(self) -> None:
        for field in self.fields.values(): # type: ignore
            widget = field.widget
            if getattr(widget, "input_type", None) == "checkbox":
                widget.attrs["class"] = (widget.attrs.get("class", "") + " form-check-input").strip()
            else:
                widget.attrs["class"] = (widget.attrs.get("class", "") + " form-control").strip()


class ClientForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            "org", "first_name", "last_name", "email", "phone",
            "address_1", "address_2", "city", "state", "zip_code",
        ]
        labels = {
            "org": "Company / Organization",
            "first_name": "First name",
            "last_name": "Last name",
            "email": "Email address",
            "phone": "Phone number",
            "address_1": "Address line 1",
            "address_2": "Address line 2",
            "city": "City",
            "state": "State / Province",
            "zip_code": "ZIP / Postal code",
        }
        help_texts = {
            "email": "Used for client communication and invoices.",
            "org": "The client’s company or organization name (if applicable).",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_bootstrap()

    # -----------------------------
    # Cleaners / normalizers
    # -----------------------------
    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip()
        return email.lower()

    def clean_state(self) -> str:
        val = (self.cleaned_data.get("state") or "").strip()
        # Standardize short codes to uppercase; leave longer names as-is
        return val.upper() if 2 <= len(val) <= 3 else val

    def clean_zip_code(self) -> str:
        val = (self.cleaned_data.get("zip_code") or "").strip()
        return val.replace(" ", "").upper() if val else val

    def clean_phone(self) -> str:
        val = (self.cleaned_data.get("phone") or "").strip()
        # Remove formatting characters (basic normalization)
        return "".join(ch for ch in val if ch.isdigit() or ch in "+") if val else val
