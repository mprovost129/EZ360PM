# company/forms.py
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from django import forms
from django.utils.translation import gettext_lazy as _
from django.core.exceptions import ValidationError

from .models import Company, CompanyInvite, CompanyMember


# ------------------------------------------------------------
# Bootstrap helpers
# ------------------------------------------------------------
class BootstrapFormMixin:
    """
    Apply Bootstrap classes to inputs, selects, checkboxes, and files.
    """
    def _init_bootstrap(self) -> None:
        for field in self.fields.values(): # type: ignore
            w = field.widget
            itype = getattr(w, "input_type", None)
            classes = w.attrs.get("class", "")

            if isinstance(w, (forms.Select, forms.SelectMultiple)):
                cls = "form-select"
            elif isinstance(w, (forms.CheckboxInput,)):
                cls = "form-check-input"
            elif isinstance(w, (forms.FileInput,)):
                cls = "form-control"
            else:
                cls = "form-control"

            w.attrs["class"] = (classes + " " + cls).strip()

        # If bound, mark invalid fields with is-invalid so Bootstrap shows feedback
        if self.is_bound: # type: ignore
            for name in self.errors: # type: ignore
                w = self.fields[name].widget # type: ignore
                w.attrs["class"] = (w.attrs.get("class", "") + " is-invalid").strip()


# ------------------------------------------------------------
# Company
# ------------------------------------------------------------
class CompanyForm(BootstrapFormMixin, forms.ModelForm):
    """
    Company form. Pass `owner=<User>` so we can show a friendly duplicate-name error
    that mirrors the (owner, name) DB unique constraint.
    """
    class Meta:
        model = Company
        fields = [
            "name", "company_logo",
            "admin_first_name", "admin_last_name", "admin_phone",
            "address_1", "address_2", "city", "state", "zip_code",
        ]
        labels = {
            "name": _("Company name"),
            "company_logo": _("Logo"),
            "admin_first_name": _("Admin first name"),
            "admin_last_name":  _("Admin last name"),
            "admin_phone":      _("Admin phone"),
            "address_1": _("Address line 1"),
            "address_2": _("Address line 2"),
            "zip_code":  _("ZIP / Postal code"),
        }
        help_texts = {
            "name": _("Shown to your team and on client-facing docs."),
        }
        widgets = {
            "company_logo": forms.ClearableFileInput(),
        }

    def __init__(self, *args, owner=None, **kwargs):
        self._owner = owner
        super().__init__(*args, **kwargs)
        self._init_bootstrap()
        self.fields["name"].widget.attrs.setdefault("placeholder", "Acme LLC")

    # --- cleaners ---------------------------------------------------------
    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise forms.ValidationError(_("Company name is required."))
        owner = self._owner or getattr(self.instance, "owner", None)
        if owner:
            qs = Company.objects.filter(owner=owner, name__iexact=name)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError(_("You already have a company with this name."))
        return name

    def clean_admin_phone(self) -> str:
        val = (self.cleaned_data.get("admin_phone") or "").strip()
        # Light normalization: keep digits and leading +
        if not val:
            return val
        normalized = []
        for ch in val:
            if ch.isdigit() or (ch == "+" and not normalized):
                normalized.append(ch)
        return "".join(normalized)

    def clean_state(self) -> str:
        val = (self.cleaned_data.get("state") or "").strip()
        # Uppercase short codes (2–3 chars), leave longer names as-is
        return val.upper() if 2 <= len(val) <= 3 else val

    def clean_zip_code(self) -> str:
        val = (self.cleaned_data.get("zip_code") or "").strip()
        # Remove spaces; uppercase for alphanumeric postal codes (e.g., Canada/UK)
        return val.replace(" ", "").upper() if val else val


# ------------------------------------------------------------
# Invite
# ------------------------------------------------------------
class InviteForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CompanyInvite
        fields = ["email", "role"]
        labels = {"email": _("Email address"), "role": _("Role")}
        widgets = {
            "email": forms.EmailInput(attrs={"autocomplete": "email"}),
            "role": forms.Select(),
        }

    def __init__(self, *args, company: Company | None = None, **kwargs):
        # Accept company in __init__ so we can validate against its members/invites
        self._company = company
        super().__init__(*args, **kwargs)
        self._init_bootstrap()

    def clean_email(self) -> str:
        return (self.cleaned_data.get("email") or "").strip().lower()

    def clean(self):
        cleaned = super().clean()
        company = self._company or getattr(self.instance, "company", None)
        email = cleaned.get("email")
        if not company or not email:
            return cleaned

        # Disallow if user with this email is already a member of the company
        from django.contrib.auth import get_user_model
        User = get_user_model()
        user = User.objects.filter(email__iexact=email).first()
        if user and CompanyMember.objects.filter(company=company, user=user).exists():
            raise ValidationError(_("This user is already a member of your company."))

        # Disallow duplicate pending invites to same email
        dup = CompanyInvite.objects.filter(company=company, email__iexact=email, status=CompanyInvite.PENDING)
        if self.instance.pk:
            dup = dup.exclude(pk=self.instance.pk)
        if dup.exists():
            raise ValidationError(_("An invitation to this email is already pending."))

        return cleaned


# ------------------------------------------------------------
# Member
# ------------------------------------------------------------
class MemberForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CompanyMember
        fields = ["role", "job_title", "hourly_rate"]
        widgets = {
            "role": forms.Select(),
            "job_title": forms.TextInput(),
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01", "min": "0"}),
        }
        labels = {
            "hourly_rate": _("Hourly rate"),
        }
        help_texts = {
            "hourly_rate": _("Optional. Used for time tracking and costing."),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._init_bootstrap()

    def clean_hourly_rate(self):
        val = self.cleaned_data.get("hourly_rate")
        if val is None:
            return val
        # Ensure non-negative and 2 decimal places
        try:
            q = Decimal(val).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        except (InvalidOperation, TypeError):
            raise ValidationError(_("Enter a valid amount."))
        if q < Decimal("0.00"):
            raise ValidationError(_("Hourly rate cannot be negative."))
        return q
