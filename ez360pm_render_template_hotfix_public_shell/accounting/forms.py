from __future__ import annotations

from django import forms


class DateRangeForm(forms.Form):
    start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))
    end = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date", "class": "form-control"}))


class LedgerAccountSelectForm(DateRangeForm):
    account_id = forms.CharField(required=False)
