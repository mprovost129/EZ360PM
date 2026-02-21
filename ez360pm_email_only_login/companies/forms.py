from __future__ import annotations

from django import forms

from .models import Company, CompanyInvite, EmployeeRole


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
