# accounts/forms.py
from __future__ import annotations

from typing import Optional

from django import forms
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.utils import timezone

from .models import User  # if you prefer, you can switch to get_user_model()

# ---------- Mixins ----------
class BootstrapFormMixin:
    def _init_bootstrap(self) -> None:
        for field in self.fields.values():  # type: ignore[assignment]
            widget = field.widget
            # Skip hidden inputs
            if getattr(widget, "input_type", "") == "hidden":
                continue
            # Checkbox vs everything else
            css = "form-check-input" if getattr(widget, "input_type", None) == "checkbox" else "form-control"
            existing = widget.attrs.get("class", "")
            widget.attrs["class"] = (existing + " " + css).strip()


# ---------- Registration ----------
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

    # Required checkboxes
    accept_terms = forms.BooleanField(required=True, label="I agree to the Terms of Service")
    accept_privacy = forms.BooleanField(required=True, label="I agree to the Privacy Policy")

    class Meta:
        model = User
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
        # Optional: enforce uniqueness explicitly (Django model already has unique=True)
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned = super().clean()
        p1: Optional[str] = cleaned.get("password1")
        p2: Optional[str] = cleaned.get("password2")

        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")

        if p1:
            # Use Django's validators
            validate_password(p1)

        return cleaned

    def save(self, commit: bool = True) -> User:
        user: User = super().save(commit=False)
        user.email = self.cleaned_data["email"].lower()
        user.set_password(self.cleaned_data["password1"])

        # Timestamp acceptance if those fields exist on your User
        if hasattr(user, "accepted_tos_at") and self.cleaned_data.get("accept_terms"):
            user.accepted_tos_at = timezone.now()  # type: ignore[attr-defined]
        if hasattr(user, "accepted_privacy_at") and self.cleaned_data.get("accept_privacy"):
            user.accepted_privacy_at = timezone.now()  # type: ignore[attr-defined]

        if commit:
            user.save()
        return user


# ---------- Login ----------
class LoginForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True})
    )
    password = forms.CharField(
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._init_bootstrap()
        self._user: Optional[User] = None

    def clean_email(self) -> str:
        # Normalize input for auth
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        email: Optional[str] = cleaned.get("email")
        password: Optional[str] = cleaned.get("password")

        if email and password:
            # Default ModelBackend expects "username", which maps to USERNAME_FIELD (email for your model)
            user = authenticate(self.request if hasattr(self, "request") else None, username=email, password=password) # type: ignore
            if user is None:
                raise forms.ValidationError("Invalid email or password.")
            if not user.is_active:
                raise forms.ValidationError("This account is inactive.")
            self._user = user # type: ignore
        return cleaned

    def get_user(self) -> Optional[User]:
        return self._user
