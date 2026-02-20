from __future__ import annotations

from django import forms

from notes.models import UserNote


class UserNoteForm(forms.ModelForm):
    class Meta:
        model = UserNote
        fields = [
            "contact_name",
            "contact_email",
            "contact_phone",
            "subject",
            "body",
        ]
        widgets = {
            "contact_name": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
            "contact_email": forms.EmailInput(attrs={"class": "form-control", "placeholder": "Optional"}),
            "contact_phone": forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional"}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": "What is this about?"}),
            "body": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Type your notes..."}),
        }

    def clean_subject(self):
        v = (self.cleaned_data.get("subject") or "").strip()
        if not v:
            raise forms.ValidationError("Subject is required.")
        return v

    def clean_body(self):
        v = (self.cleaned_data.get("body") or "").strip()
        if not v:
            raise forms.ValidationError("Notes are required.")
        return v
