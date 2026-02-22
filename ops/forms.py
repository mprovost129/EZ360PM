from __future__ import annotations

from django import forms

from companies.models import Company
from billing.models import PlanCatalog, SeatAddonConfig
from .models import ReleaseNote, SiteConfig, OpsAlertLevel, QAIssue


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
    run_recommended = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={"class": "form-check-input"}),
        help_text="Runs the recommended launch checks (readiness + template/url sanity + invariants/idempotency). Smoke Test runs only when a company is selected.",
    )

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

        # Convenience: Run Recommended.
        if cleaned.get("run_recommended"):
            cleaned["run_invariants"] = True
            cleaned["run_idempotency"] = True
            cleaned["run_template_sanity"] = True
            cleaned["run_url_sanity"] = True
            cleaned["run_readiness"] = True
            cleaned["run_smoke"] = bool(company)

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


class QAIssueForm(forms.ModelForm):
    class Meta:
        model = QAIssue
        fields = [
            "company",
            "status",
            "severity",
            "area",
            "title",
            "description",
            "related_url",
            "steps_to_reproduce",
            "expected_behavior",
            "actual_behavior",
            "discovered_by_email",
            "assigned_to_email",
            "resolution_notes",
        ]
        widgets = {
            "company": forms.Select(attrs={"class": "form-select"}),
            "status": forms.Select(attrs={"class": "form-select"}),
            "severity": forms.Select(attrs={"class": "form-select"}),
            "area": forms.TextInput(attrs={"class": "form-control", "placeholder": "Invoices / Banking / Time / …"}),
            "title": forms.TextInput(attrs={"class": "form-control"}),
            "description": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "related_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://..."}),
            "steps_to_reproduce": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "expected_behavior": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "actual_behavior": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
            "discovered_by_email": forms.EmailInput(attrs={"class": "form-control"}),
            "assigned_to_email": forms.EmailInput(attrs={"class": "form-control"}),
            "resolution_notes": forms.Textarea(attrs={"class": "form-control", "rows": 3}),
        }

class OpsAlertRoutingForm(forms.ModelForm):
    class Meta:
        model = SiteConfig
        fields = [
            "ops_alert_webhook_enabled",
            "ops_alert_webhook_url",
            "ops_alert_webhook_timeout_seconds",
            "ops_alert_email_enabled",
            "ops_alert_email_recipients",
            "ops_alert_email_min_level",
            "ops_alert_noise_path_prefixes",
            "ops_alert_noise_user_agents",
            "ops_alert_dedup_minutes",
            "ops_alert_prune_resolved_after_days",
            "ops_snooze_prune_after_days",
            "maintenance_mode_enabled",
            "maintenance_message",
            "maintenance_allow_staff",
            "billing_trial_days",

            # Stripe mirror health / drift detection
            "stripe_mirror_stale_after_hours",
            "stripe_mirror_stale_alert_level",

            # Ops governance
            "ops_require_2fa_for_critical_actions",
            "ops_two_person_approval_enabled",

            # Tenant risk scoring
            "risk_payment_failed_window_days",
            "risk_trial_ends_within_days",
            "risk_weight_past_due",
            "risk_weight_mirror_stale",
            "risk_weight_payment_failed",
            "risk_weight_payment_failed_sub_only",
            "risk_weight_canceling",
            "risk_weight_trial_ends_soon",
            "risk_level_medium_threshold",
            "risk_level_high_threshold",

            "ops_notify_email_enabled",
            "ops_notify_email_recipients",
            "ops_notify_on_company_signup",
            "ops_notify_on_subscription_active",
        ]
        widgets = {
            "ops_alert_webhook_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ops_alert_webhook_url": forms.URLInput(attrs={"class": "form-control", "placeholder": "https://…"}),
            "ops_alert_webhook_timeout_seconds": forms.NumberInput(attrs={"class": "form-control", "step": "0.1", "min": "0.1"}),
            "ops_alert_email_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ops_alert_email_recipients": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "ops@example.com, admin@example.com"}),
            "ops_alert_email_min_level": forms.Select(attrs={"class": "form-select"}),
            "ops_alert_noise_path_prefixes": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "/wp-login.php\n/.env\n/robots.txt"}),
            "ops_alert_noise_user_agents": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "AhrefsBot\nSemrushBot\nMJ12bot"}),
            "ops_alert_dedup_minutes": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 1440}),
            "ops_alert_prune_resolved_after_days": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 365}),
            "ops_snooze_prune_after_days": forms.NumberInput(attrs={"class": "form-control", "min": "0"}),
            "maintenance_mode_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "maintenance_allow_staff": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "maintenance_message": forms.Textarea(attrs={"class": "form-control", "rows": 4, "placeholder": "Optional message shown during maintenance…"}),
            "billing_trial_days": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "365"}),

            "stripe_mirror_stale_after_hours": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "720"}),
            "stripe_mirror_stale_alert_level": forms.Select(attrs={"class": "form-select"}),
            "ops_require_2fa_for_critical_actions": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ops_two_person_approval_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "risk_payment_failed_window_days": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "90"}),
            "risk_trial_ends_within_days": forms.NumberInput(attrs={"class": "form-control", "min": "1", "max": "30"}),
            "risk_weight_past_due": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "risk_weight_mirror_stale": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "risk_weight_payment_failed": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "risk_weight_payment_failed_sub_only": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "risk_weight_canceling": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "risk_weight_trial_ends_soon": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "risk_level_medium_threshold": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),
            "risk_level_high_threshold": forms.NumberInput(attrs={"class": "form-control", "min": "0", "max": "100"}),

            "ops_notify_email_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ops_notify_email_recipients": forms.Textarea(attrs={"class": "form-control", "rows": 2, "placeholder": "ops@example.com, admin@example.com"}),
            "ops_notify_on_company_signup": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "ops_notify_on_subscription_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("ops_alert_webhook_enabled") and not (cleaned.get("ops_alert_webhook_url") or "").strip():
            self.add_error("ops_alert_webhook_url", "Webhook URL is required when webhook routing is enabled.")
        return cleaned


class PlanCatalogForm(forms.ModelForm):
    class Meta:
        model = PlanCatalog
        fields = [
            "code",
            "name",
            "is_active",
            "sort_order",
            "monthly_price",
            "annual_price",
            "included_seats",
            "trial_days",
            "stripe_monthly_price_id",
            "stripe_annual_price_id",
        ]
        widgets = {
            # Code is immutable; render as a hidden field and display a badge in the template.
            # (Disabled <select> fields look like dropdowns but don't open and don't submit.)
            "code": forms.HiddenInput(),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "sort_order": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 999}),
            "monthly_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "annual_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "included_seats": forms.NumberInput(attrs={"class": "form-control", "min": 1, "max": 999}),
            "trial_days": forms.NumberInput(attrs={"class": "form-control", "min": 0, "max": 365}),
            "stripe_monthly_price_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "price_..."}),
            "stripe_annual_price_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "price_..."}),
        }

    def clean_code(self):
        # Code is immutable; ignore any POST value.
        return self.instance.code


class SeatAddonConfigForm(forms.ModelForm):
    class Meta:
        model = SeatAddonConfig
        fields = [
            "monthly_price",
            "annual_price",
            "stripe_monthly_price_id",
            "stripe_annual_price_id",
        ]
        widgets = {
            "monthly_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "annual_price": forms.NumberInput(attrs={"class": "form-control", "step": "0.01", "min": "0"}),
            "stripe_monthly_price_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "price_..."}),
            "stripe_annual_price_id": forms.TextInput(attrs={"class": "form-control", "placeholder": "price_..."}),
        }

class OpsRoleGrantForm(forms.Form):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={"class": "form-control", "placeholder": "staff@ez360pm.com"}),
        help_text="Email of an existing staff user.",
    )
    role = forms.ChoiceField(
        required=True,
        choices=[],
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "Optional notes"}),
    )

    def __init__(self, *args, **kwargs):
        from .models import OpsRole
        super().__init__(*args, **kwargs)
        self.fields["role"].choices = OpsRole.choices