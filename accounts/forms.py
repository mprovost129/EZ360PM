# accounts/forms.py
from __future__ import annotations

from typing import Optional

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from core.utils import TIMEZONE_CHOICES, US_STATE_CHOICES
from localflavor.us.forms import USStateField, USStateSelect

from .models import UserProfile

UserModel = get_user_model()


# ---------------------------------------------------------------------
# Mixins
# ---------------------------------------------------------------------
class BootstrapFormMixin:
    """
    Apply Bootstrap 5 classes to widgets automatically.
    - Inputs/Textareas/File: form-control
    - Select/SelectMultiple: form-select
    - Checkbox/Radio: form-check-input
    Skips hidden inputs and preserves any existing classes.
    """
    def _init_bootstrap(self) -> None:
        for field in self.fields.values():  # type: ignore[assignment]
            widget = field.widget
            input_type = getattr(widget, "input_type", "")
            if input_type == "hidden":
                continue

            # Map widget classes
            if isinstance(widget, (forms.Select, forms.SelectMultiple)):
                css = "form-select"
            elif isinstance(widget, (forms.CheckboxInput, forms.RadioSelect)):
                css = "form-check-input"
            else:
                # TextInput, Textarea, PasswordInput, EmailInput, ClearableFileInput, etc.
                css = "form-control"

            existing = widget.attrs.get("class", "")
            # Avoid duplicates while preserving custom classes
            widget.attrs["class"] = (" ".join({*existing.split(), css})).strip()


# ---------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------
class RegisterForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )
    password2 = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    # Required checkboxes (not model fields)
    accept_terms = forms.BooleanField(required=True, label="I agree to the Terms of Service")
    accept_privacy = forms.BooleanField(required=True, label="I agree to the Privacy Policy")

    class Meta:
        model = UserModel
        fields = ["email", "name"]  # passwords & checkboxes are explicit fields
        widgets = {
            "email": forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_bootstrap()

    def clean_email(self) -> str:
        email = (self.cleaned_data.get("email") or "").strip().lower()
        if not email:
            raise forms.ValidationError("Email is required.")
        # Defensive case-insensitive uniqueness check (model also enforces)
        if UserModel._default_manager.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1: Optional[str] = cleaned.get("password1")
        p2: Optional[str] = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")

        if p1:
            validate_password(p1)

        return cleaned

    def save(self, commit: bool = True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower()
        user.set_password(self.cleaned_data["password1"])

        # Timestamp acceptance if present on the model
        if hasattr(user, "accepted_tos_at") and self.cleaned_data.get("accept_terms"):
            user.accepted_tos_at = timezone.now()  # type: ignore[attr-defined]
        if hasattr(user, "accepted_privacy_at") and self.cleaned_data.get("accept_privacy"):
            user.accepted_privacy_at = timezone.now()  # type: ignore[attr-defined]

        if commit:
            user.save()
        return user


# ---------------------------------------------------------------------
# Login
# ---------------------------------------------------------------------
class LoginForm(forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": "form-control"}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": "form-control"}))

    def __init__(self, *args, request=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request  # keep request so authenticate can use it

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if not email or not password:
            return cleaned

        # IMPORTANT: use username=email (USERNAME_FIELD is 'email')
        user = authenticate(self.request, username=email, password=password)
        if user is None:
            raise forms.ValidationError(_("Invalid email or password."))
        if not getattr(user, "is_active", True):
            raise forms.ValidationError(_("This account is inactive."))

        cleaned["user"] = user  # so the view can login(request, cleaned["user"])
        return cleaned


# ---------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------
class UserProfileForm(BootstrapFormMixin, forms.ModelForm):
    """
    Profile fields + optional helpers for first/last name.
    Views will combine these into your single User.name field.
    """
    first_name = forms.CharField(
        required=False, label="First name",
        widget=forms.TextInput(attrs={"autocomplete": "given-name"})
    )
    last_name = forms.CharField(
        required=False, label="Last name",
        widget=forms.TextInput(attrs={"autocomplete": "family-name"})
    )
    timezone = forms.ChoiceField(
        choices=TIMEZONE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )
    state = forms.ChoiceField(   # if your model has a `state` CharField
        choices=US_STATE_CHOICES,
        required=False,
        widget=forms.Select(attrs={"class": "form-select"})
    )
    state = USStateField(required=False, widget=USStateSelect(attrs={"class": "form-select"}))

    class Meta:
        model = UserProfile
        fields = [
            "first_name", "last_name", "title", "phone",
            "timezone", "locale", "dark_mode", "avatar", "bio",
            "state",  # include if present on the model
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": "form-control"}),
            "last_name": forms.TextInput(attrs={"class": "form-control"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "phone": forms.TextInput(attrs={"class": "form-control"}),
            "locale": forms.TextInput(attrs={"class": "form-control"}),
            "dark_mode": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "avatar": forms.ClearableFileInput(attrs={"class": "form-control"}),
            "bio": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
        }

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_bootstrap()
