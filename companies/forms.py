from __future__ import annotations

from django import forms

from .models import Company, CompanyInvite, EmployeeRole

try:
    from documents.models import NumberingScheme
except Exception:  # pragma: no cover
    NumberingScheme = None  # type: ignore


class CompanyCreateForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = [
            "name",
            "logo",
            "email_from_name",
            "email_from_address",
            "address1",
            "address2",
            "city",
            "state",
            "zip_code",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "email_from_name": forms.TextInput(attrs={"class": "form-control"}),
            "email_from_address": forms.EmailInput(attrs={"class": "form-control"}),
            "address1": forms.TextInput(attrs={"class": "form-control"}),
            "address2": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control", "maxlength": "2"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control"}),
        }


class CompanyInviteForm(forms.ModelForm):
    class Meta:
        model = CompanyInvite
        fields = ["email", "username_public", "role"]
        widgets = {
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "name@example.com"}),
            "username_public": forms.TextInput(attrs={"class": "form-control", "maxlength": "40"}),
            "role": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_role(self):
        role = self.cleaned_data.get("role") or EmployeeRole.STAFF
        # safety: do not allow creating owner invites via UI
        if role == EmployeeRole.OWNER:
            return EmployeeRole.ADMIN
        return role


class CompanySettingsForm(forms.ModelForm):
    """Company settings editable in the dashboard (branding + contact)."""

    class Meta:
        model = Company
        fields = [
            "name",
            "logo",
            "email_from_name",
            "email_from_address",
            "address1",
            "address2",
            "city",
            "state",
            "zip_code",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "logo": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "email_from_name": forms.TextInput(attrs={"class": "form-control"}),
            "email_from_address": forms.EmailInput(attrs={"class": "form-control"}),
            "address1": forms.TextInput(attrs={"class": "form-control"}),
            "address2": forms.TextInput(attrs={"class": "form-control"}),
            "city": forms.TextInput(attrs={"class": "form-control"}),
            "state": forms.TextInput(attrs={"class": "form-control", "maxlength": "2"}),
            "zip_code": forms.TextInput(attrs={"class": "form-control"}),
        }


class NumberingSchemeForm(forms.ModelForm):
    """Company document numbering configuration (invoice/estimate/proposal)."""

    class Meta:
        model = NumberingScheme
        fields = [
            "invoice_pattern",
            "invoice_reset",
            "invoice_seq",
            "estimate_pattern",
            "estimate_reset",
            "estimate_seq",
            "proposal_pattern",
            "proposal_reset",
            "proposal_seq",
        ]
        widgets = {
            "invoice_pattern": forms.TextInput(attrs={"class": "form-control", "placeholder": "{YY}/{MM}/{SEQ:3}"}),
            "estimate_pattern": forms.TextInput(attrs={"class": "form-control", "placeholder": "{YY}/{MM}/{SEQ:3}"}),
            "proposal_pattern": forms.TextInput(attrs={"class": "form-control", "placeholder": "{YY}/{MM}/{SEQ:3}"}),
            "invoice_reset": forms.Select(attrs={"class": "form-select"}),
            "estimate_reset": forms.Select(attrs={"class": "form-select"}),
            "proposal_reset": forms.Select(attrs={"class": "form-select"}),
            "invoice_seq": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "estimate_seq": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
            "proposal_seq": forms.NumberInput(attrs={"class": "form-control", "min": "1"}),
        }

    def clean_invoice_seq(self):
        v = int(self.cleaned_data.get("invoice_seq") or 1)
        return max(v, 1)

    def clean_estimate_seq(self):
        v = int(self.cleaned_data.get("estimate_seq") or 1)
        return max(v, 1)

    def clean_proposal_seq(self):
        v = int(self.cleaned_data.get("proposal_seq") or 1)
        return max(v, 1)
