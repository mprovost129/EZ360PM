# core/forms.py
from __future__ import annotations

from django import forms
from django.core.validators import validate_email
from django.utils.translation import gettext_lazy as _

from .models import Suggestion


# -------------------------------------------------------------------
# Email helper
# -------------------------------------------------------------------

class SendEmailForm(forms.Form):
    """
    Generic form to send an email (e.g., from admin UI).
    Provides To/CC/Subject/Message fields with Bootstrap styling.
    """

    to = forms.EmailField(
        label=_("To"),
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": _("recipient@example.com")}),
    )
    cc = forms.CharField(
        label=_("CC"),
        required=False,
        help_text=_("Comma-separated emails"),
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("cc1@example.com, cc2@example.com")}),
    )
    subject = forms.CharField(
        label=_("Subject"),
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": _("Subject")}),
    )
    message = forms.CharField(
        label=_("Message"),
        required=False,
        widget=forms.Textarea(attrs={"rows": 6, "class": "form-control", "placeholder": _("Write your message...")}),
    )

    def clean_cc(self) -> list[str]:
        """
        Parse CC into a list of valid emails.
        Accepts commas, semicolons, or newlines as separators.
        """
        data = self.cleaned_data.get("cc", "")
        if not data:
            return []
        parts = [p.strip() for p in data.replace(";", ",").replace("\n", ",").split(",") if p.strip()]
        for email in parts:
            validate_email(email)
        return parts


# -------------------------------------------------------------------
# Suggestions / Feedback
# -------------------------------------------------------------------

class SuggestionForm(forms.ModelForm):
    """
    Form for anonymous or logged-in users to send feedback/suggestions.
    """

    class Meta:
        model = Suggestion
        fields = ["name", "email", "subject", "message", "page_url"]
        widgets = {
            "name": forms.TextInput(attrs={"class": "form-control", "placeholder": _("Your name")}),
            "email": forms.EmailInput(attrs={"class": "form-control", "placeholder": _("you@example.com")}),
            "subject": forms.TextInput(attrs={"class": "form-control", "placeholder": _("Subject")}),
            "message": forms.Textarea(attrs={"rows": 5, "class": "form-control", "placeholder": _("Your message")}),
            "page_url": forms.HiddenInput(),
        }
        labels = {
            "name": _("Name"),
            "email": _("Email"),
            "subject": _("Subject"),
            "message": _("Message"),
        }

