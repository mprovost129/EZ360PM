from __future__ import annotations

from django import forms

from companies.models import Company
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
    company_id = forms.UUIDField(required=True, widget=forms.HiddenInput())


class DriftLinkPaymentForm(forms.Form):
    company_id = forms.UUIDField(required=True, widget=forms.HiddenInput())
    payment_id = forms.UUIDField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "payment uuid"}),
    )
    invoice_id = forms.UUIDField(
        required=True,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "invoice uuid"}),
    )


class OpsEmailTestForm(forms.Form):
    to_email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "you@yourdomain.com"}),
    )
    subject = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "EZ360PM test email"}),
    )
    message = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Optional message"}),
    )


class OpsChecksForm(forms.Form):
    company = forms.ModelChoiceField(
        required=False,
        queryset=Company.objects.all().order_by("-created_at")[:250],
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Optional. Limit checks to one company (required for Smoke Test).",
    )

    run_smoke = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    run_all = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Runs all checks. If no company is selected, Smoke Test is skipped.",
    )
    run_invariants = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    run_idempotency = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    run_template_sanity = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    run_url_sanity = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))
    run_readiness = forms.BooleanField(required=False, widget=forms.CheckboxInput(attrs={"class": "form-check-input"}))

    fail_fast = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Stop on first failure (where supported).",
    )
    quiet = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Reduce output (CI-style).",
    )

    def clean(self):
        cleaned = super().clean()
        company = cleaned.get("company")

        # Convenience: Run All.
        if cleaned.get("run_all"):
            cleaned["run_invariants"] = True
            cleaned["run_idempotency"] = True
            cleaned["run_template_sanity"] = True
            cleaned["run_url_sanity"] = True
            cleaned["run_readiness"] = True
            # Smoke test is company-scoped.
            cleaned["run_smoke"] = bool(company)

        run_smoke = bool(cleaned.get("run_smoke"))
        if run_smoke and not company:
            self.add_error("company", "Select a company to run the smoke test.")
        return cleaned
