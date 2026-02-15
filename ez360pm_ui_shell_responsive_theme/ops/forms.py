from __future__ import annotations

from django import forms

from .models import ReleaseNote


class ReleaseNoteForm(forms.ModelForm):
    class Meta:
        model = ReleaseNote
        fields = [
            "environment",
            "build_version",
            "build_sha",
            "title",
            "notes",
            "is_published",
        ]
        widgets = {
            "environment": forms.TextInput(attrs={"class": "form-control", "placeholder": "prod / staging / dev"}),
            "build_version": forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 1.2.3"}),
            "build_sha": forms.TextInput(attrs={"class": "form-control", "placeholder": "git sha"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "rows": 6}),
            "is_published": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class DriftCompanyActionForm(forms.Form):
    company_id = forms.IntegerField(required=True, widget=forms.HiddenInput())


class DriftLinkPaymentForm(forms.Form):
    company_id = forms.IntegerField(required=True, widget=forms.HiddenInput())
    payment_id = forms.UUIDField(required=True, widget=forms.TextInput(attrs={"class":"form-control","placeholder":"payment uuid"}))
    invoice_id = forms.UUIDField(required=True, widget=forms.TextInput(attrs={"class":"form-control","placeholder":"invoice uuid"}))

