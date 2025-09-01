from __future__ import annotations

from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.forms import inlineformset_factory
from django.utils import timezone

from .models import (
    Client,
    Company,
    CompanyInvite,
    CompanyMember,
    Estimate,
    EstimateItem,
    Expense,
    Invoice,
    InvoiceItem,
    Payment,
    Project,
    RecurringPlan,
    Suggestion,
    TimeEntry,
    UserProfile,
)


# -----------------------------
# Clients
# -----------------------------

class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = ["first_name", "last_name", "org", "email", "phone", "address"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
        }


# -----------------------------
# Projects
# -----------------------------

class ProjectForm(forms.ModelForm):
    """
    Pass `company` in __init__ to scope `team` choices to members of that company.
    """
    class Meta:
        model = Project
        fields = [
            "client",
            "number",
            "name",
            "details",
            "billing_type",
            "budget",
            "start_date",
            "due_date",
            "estimated_hours",
            "team",
        ]
        widgets = {
            "details": forms.Textarea(attrs={"rows": 4}),
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
            "team": forms.SelectMultiple(attrs={"size": 6}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        # Helpful numeric steps in browsers
        self.fields["budget"].widget = forms.NumberInput(attrs={"step": "0.01"})
        self.fields["estimated_hours"].widget = forms.NumberInput(attrs={"step": "0.25"})
        if company:
            self.fields["client"].queryset = Client.objects.filter(company=company) # type: ignore
            # Team = company members' users
            member_user_ids = CompanyMember.objects.filter(company=company).values_list("user_id", flat=True)
            self.fields["team"].queryset = get_user_model().objects.filter(id__in=member_user_ids).order_by("email") # type: ignore


# -----------------------------
# Time Tracking
# -----------------------------

class TimeEntryForm(forms.ModelForm):
    class Meta:
        model = TimeEntry
        fields = ["notes", "hours", "started_at", "ended_at"]
        widgets = {
            "started_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "ended_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-control"}),
            "hours": forms.NumberInput(attrs={"step": "0.01", "class": "form-control"}),
            "notes": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
        }

    def clean(self):
        data = super().clean()
        start = data.get("started_at")
        end = data.get("ended_at")
        if start and end and end < start:
            self.add_error("ended_at", "End time cannot be before start time.")
        return data


# -----------------------------
# Invoices & Items
# -----------------------------

class InvoiceForm(forms.ModelForm):
    class Meta:
        model = Invoice
        fields = ["project", "client", "number", "status", "issue_date", "due_date", "notes", "tax"]
        widgets = {
            "notes": forms.Textarea(attrs={"rows": 3}),
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "due_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields["client"].queryset = Client.objects.filter(company=company) # type: ignore
            self.fields["project"].queryset = Project.objects.filter(company=company) # type: ignore
        if self.instance.pk is None and not self.initial.get("tax"):
            self.initial["tax"] = Decimal("0.00")

    def clean(self):
        data = super().clean()
        issue = data.get("issue_date")
        due = data.get("due_date")
        if issue and due and due < issue:
            self.add_error("due_date", "Due date cannot be before the issue date.")
        return data


class InvoiceItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceItem
        fields = ["description", "qty", "unit_price"]
        widgets = {
            "description": forms.TextInput(attrs={"placeholder": "Description"}),
        }


InvoiceItemFormSet = inlineformset_factory(
    Invoice,
    InvoiceItem,
    form=InvoiceItemForm,
    extra=3,
    can_delete=True,
)


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "received_at", "method"]
        widgets = {
            "received_at": forms.DateTimeInput(attrs={"type": "datetime-local"}),
        }


# -----------------------------
# Expenses
# -----------------------------

class ExpenseForm(forms.ModelForm):
    class Meta:
        model = Expense
        fields = [
            "project",
            "date",
            "amount",
            "description",
            "vendor",
            "category",
            "is_billable",
            "billable_markup_pct",
            "billable_note",
        ]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields["project"].queryset = Project.objects.filter(company=company).order_by("-created_at") # type: ignore
        # Nice number steppers
        self.fields["amount"].widget = forms.NumberInput(attrs={"step": "0.01"})
        self.fields["billable_markup_pct"].widget = forms.NumberInput(attrs={"step": "0.01"})


# -----------------------------
# Company / Invites
# -----------------------------

class CompanyForm(forms.ModelForm):
    class Meta:
        model = Company
        fields = ["name", "logo", "address", "phone"]
        widgets = {"address": forms.Textarea(attrs={"rows": 3})}


class InviteForm(forms.ModelForm):
    class Meta:
        model = CompanyInvite
        fields = ["email", "role"]


# -----------------------------
# Estimates & Items
# -----------------------------

class EstimateForm(forms.ModelForm):
    class Meta:
        model = Estimate
        fields = [
            "client",
            "project",
            "number",
            "status",
            "issue_date",
            "valid_until",
            "tax",
            "notes",
            "is_template",
        ]
        widgets = {
            "issue_date": forms.DateInput(attrs={"type": "date"}),
            "valid_until": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields["client"].queryset = Client.objects.filter(company=company) # type: ignore
            self.fields["project"].queryset = Project.objects.filter(company=company) # type: ignore

    def clean(self):
        data = super().clean()
        issue = data.get("issue_date")
        valid_until = data.get("valid_until")
        if issue and valid_until and valid_until < issue:
            self.add_error("valid_until", "Valid until date cannot be before the issue date.")
        return data


class EstimateItemForm(forms.ModelForm):
    class Meta:
        model = EstimateItem
        fields = ["description", "qty", "unit_price"]


EstimateItemFormSet = inlineformset_factory(
    Estimate,
    EstimateItem,
    form=EstimateItemForm,
    extra=3,
    can_delete=True,
)


# -----------------------------
# Email helper
# -----------------------------

class SendEmailForm(forms.Form):
    to = forms.EmailField(label="To")
    cc = forms.CharField(label="CC", required=False, help_text="Comma-separated emails")
    subject = forms.CharField()
    message = forms.CharField(widget=forms.Textarea, required=False)


# -----------------------------
# Recurring Plans
# -----------------------------

class RecurringPlanForm(forms.ModelForm):
    class Meta:
        model = RecurringPlan
        fields = [
            "title",
            "client",
            "project",
            "template_invoice",
            "frequency",
            "start_date",
            "next_run_date",
            "end_date",
            "due_days",
            "status",
            "auto_email",
            "max_occurrences",
        ]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "next_run_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        super().__init__(*args, **kwargs)
        if company:
            self.fields["client"].queryset = Client.objects.filter(company=company) # type: ignore
            self.fields["project"].queryset = Project.objects.filter(company=company) # type: ignore
            self.fields["template_invoice"].queryset = Invoice.objects.filter(company=company) # type: ignore


# -----------------------------
# Profile & Members
# -----------------------------

class UserProfileForm(forms.ModelForm):
    # Also edit basic User fields inline (if your User model supports them).
    first_name = forms.CharField(required=False, label="First name")
    last_name = forms.CharField(required=False, label="Last name")

    class Meta:
        model = UserProfile
        fields = ["avatar", "phone", "title", "timezone", "locale", "bio", "dark_mode"]
        widgets = {
            "bio": forms.Textarea(attrs={"rows": 4}),
        }


class MemberForm(forms.ModelForm):
    class Meta:
        model = CompanyMember
        fields = ["role", "job_title", "hourly_rate"]
        widgets = {
            "hourly_rate": forms.NumberInput(attrs={"step": "0.01"}),
        }


# -----------------------------
# Estimate → Project wizard
# -----------------------------

class ConvertEstimateToProjectForm(forms.Form):
    MODE_NEW = "new"
    MODE_ATTACH = "attach"

    mode = forms.ChoiceField(
        choices=[(MODE_NEW, "Create new project"), (MODE_ATTACH, "Attach to existing project")],
        widget=forms.RadioSelect,
        initial=MODE_NEW,
    )

    # Existing project (filtered in __init__)
    existing_project = forms.ModelChoiceField(
        queryset=Project.objects.none(),
        required=False,
        empty_label="— Select a project —",
    )

    # New project fields
    new_number = forms.CharField(required=False, label="Project #")
    new_name = forms.CharField(required=False, label="Project name")
    new_billing_type = forms.ChoiceField(
        choices=[(Project.HOURLY, "Hourly"), (Project.FLAT, "Flat rate")],
        required=False,
        initial=Project.HOURLY,
    )
    new_estimated_hours = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=9)
    new_budget = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=12)
    new_start_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    new_due_date = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        client = kwargs.pop("client", None)
        super().__init__(*args, **kwargs)
        qs = Project.objects.none()
        if company:
            qs = Project.objects.filter(company=company).order_by("-created_at")
            if client:
                qs = qs.filter(client=client)
        self.fields["existing_project"].queryset = qs # type: ignore

    def clean(self):
        data = super().clean()
        mode = data.get("mode")
        if mode == self.MODE_ATTACH:
            if not data.get("existing_project"):
                self.add_error("existing_project", "Choose a project to attach to.")
        else:
            # New project — require essential fields
            if not data.get("new_name"):
                self.add_error("new_name", "Project name is required.")
            if not data.get("new_billing_type"):
                self.add_error("new_billing_type", "Select a billing type.")
            start = data.get("new_start_date")
            due = data.get("new_due_date")
            if start and due and due < start:
                self.add_error("new_due_date", "Due date cannot be before start date.")
        return data


# -----------------------------
# Time → Invoice wizard
# -----------------------------

class TimeToInvoiceForm(forms.Form):
    ROUNDING_CHOICES = [
        ("none", "No rounding"),
        ("0.05", "Nearest 0.05 h (3 min)"),
        ("0.1", "Nearest 0.1 h (6 min)"),
        ("0.25", "Nearest 0.25 h (15 min)"),
        ("0.5", "Nearest 0.5 h (30 min)"),
        ("1", "Nearest 1.0 h"),
    ]
    GROUPING_CHOICES = [
        ("project", "Single line (all time)"),
        ("day", "One line per day"),
        ("user", "One line per user"),
        ("entry", "One line per entry"),
    ]

    start = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    rounding = forms.ChoiceField(choices=ROUNDING_CHOICES, initial="0.25")
    group_by = forms.ChoiceField(choices=GROUPING_CHOICES, initial="day")
    override_rate = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=10,
        help_text="Leave blank to use project hourly rate.",
    )
    description = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Shown on invoice lines (prefix).",
    )
    include_expenses = forms.BooleanField(required=False, initial=True, label="Include billable expenses")
    include_only_approved = forms.BooleanField(required=False, initial=True, label="Only include approved time")

    EXPENSE_GROUPING_CHOICES = [
        ("all", "Single line: all expenses (summed)"),
        ("category", "Group by category"),
        ("vendor", "Group by vendor"),
        ("expense", "One line per expense"),
    ]
    expense_group_by = forms.ChoiceField(choices=EXPENSE_GROUPING_CHOICES, initial="category", required=False)
    expense_markup_override = forms.DecimalField(
        required=False,
        min_value=0,
        decimal_places=2,
        max_digits=5,
        help_text="Optional % markup to override per-expense markup (e.g., 10.00 for 10%).",
    )
    expense_label_prefix = forms.CharField(
        required=False,
        max_length=80,
        help_text="Optional label prefix, e.g., 'Reimbursable expense'.",
    )

    def clean(self):
        data = super().clean()
        start = data.get("start")
        end = data.get("end")
        if start and end and end < start:
            self.add_error("end", "End date cannot be before start date.")
        return data


# -----------------------------
# Timesheets
# -----------------------------

class TimesheetWeekForm(forms.Form):
    week = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    project = forms.ModelChoiceField(queryset=Project.objects.none(), label="Project")
    mon = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=6, label="Mon")
    tue = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=6, label="Tue")
    wed = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=6, label="Wed")
    thu = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=6, label="Thu")
    fri = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=6, label="Fri")
    sat = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=6, label="Sat")
    sun = forms.DecimalField(required=False, min_value=0, decimal_places=2, max_digits=6, label="Sun")
    note = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
        help_text="Optional note applied to created/updated entries.",
    )

    def __init__(self, *args, **kwargs):
        company = kwargs.pop("company", None)
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        qs = Project.objects.none()
        if company:
            base = Project.objects.filter(company=company).order_by("-created_at")
            if user is not None:
                team_qs = base.filter(team=user).distinct()
                qs = team_qs if team_qs.exists() else base
            else:
                qs = base
        self.fields["project"].queryset = qs # type: ignore


class TimesheetSubmitForm(forms.Form):
    week = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))


# -----------------------------
# Refunds
# -----------------------------

class RefundForm(forms.Form):
    amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=Decimal("0.01"),
        help_text="Refund amount",
    )
    use_stripe = forms.BooleanField(
        required=False,
        initial=False,
        help_text="Issue a Stripe refund to the card (requires a Stripe payment).",
    )
    payment_intent = forms.ChoiceField(
        required=False,
        help_text="Which Stripe payment to refund?",
    )

    def __init__(self, *args, **kwargs):
        invoice = kwargs.pop("invoice", None)
        super().__init__(*args, **kwargs)

        # Build choices from recorded Stripe payments (external_id = PaymentIntent id)
        pis = []
        if invoice:
            for p in invoice.payments.filter(method__iexact="stripe").exclude(external_id=""):
                label = f"{p.external_id} — ${p.amount}"
                pis.append((p.external_id, label))

        if pis:
            self.fields["payment_intent"].choices = pis
        else:
            # No Stripe payments → hide Stripe-specific fields
            self.fields.pop("payment_intent", None)
            self.fields.pop("use_stripe", None)


# -----------------------------
# Suggestions / Feedback
# -----------------------------

class SuggestionForm(forms.ModelForm):
    class Meta:
        model = Suggestion
        fields = ["name", "email", "subject", "message", "page_url"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5}),
            "page_url": forms.HiddenInput(),
        }
