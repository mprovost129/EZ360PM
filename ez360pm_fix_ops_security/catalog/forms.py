from __future__ import annotations

from django import forms

from core.forms.money import MoneyCentsField

from .models import CatalogItem, CatalogItemType, TaxBehavior


class CatalogItemForm(forms.ModelForm):
    unit_price_cents = MoneyCentsField(label="Unit price")

    class Meta:
        model = CatalogItem
        fields = ["item_type", "name", "description", "unit_price_cents", "tax_behavior", "is_active"]
        widgets = {
            "item_type": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "tax_behavior": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Ensure the money field uses Bootstrap
        self.fields["unit_price_cents"].widget.attrs.setdefault("class", "form-control")
