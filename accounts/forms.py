# accounts/forms.py
from django import forms
from django.contrib.auth import authenticate
from .models import User
from django.utils import timezone
    

class BootstrapFormMixin:
    def _init_bootstrap(self):
        for _, field in self.fields.items(): # type: ignore
            widget = field.widget
            if getattr(widget, 'input_type', '') == 'hidden':
                continue
            if getattr(widget, 'input_type', None) == 'checkbox':
                css = 'form-check-input'
            else:
                css = 'form-control'
            existing = widget.attrs.get('class', '')
            widget.attrs['class'] = (existing + ' ' + css).strip()

class RegisterForm(BootstrapFormMixin, forms.ModelForm):
    password1 = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )
    password2 = forms.CharField(
        label="Confirm password",
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"})
    )

    # NEW: required checkboxes
    accept_terms = forms.BooleanField(required=True, label="I agree to the Terms of Service")
    accept_privacy = forms.BooleanField(required=True, label="I agree to the Privacy Policy")

    class Meta:
        model = User
        fields = ["email", "name"]  # checkboxes and passwords are added manually
        widgets = {
            "email": forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}),
            "name": forms.TextInput(attrs={"autocomplete": "name"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_bootstrap()

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get("password1")
        p2 = cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            self.add_error("password2", "Passwords do not match.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])

        # Optional: if you later add these fields to your User/UserProfile,
        # we’ll set them when present and ignore otherwise.
        for field_name in ("accepted_tos_at", "accepted_privacy_at"):
            if hasattr(user, field_name):
                setattr(user, field_name, timezone.now())

        if commit:
            user.save()
        return user


class LoginForm(BootstrapFormMixin, forms.Form):
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email", "autofocus": True}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_bootstrap()
        self.user = None

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get("email")
        password = cleaned.get("password")
        if email and password:
            user = authenticate(email=email, password=password)
            if user is None:
                raise forms.ValidationError("Invalid email or password.")
            if not user.is_active:
                raise forms.ValidationError("This account is inactive.")
            self.user = user
        return cleaned

    def get_user(self):
        return self.user