from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models
from django.urls import reverse
from django.utils import timezone


UserModelRef = settings.AUTH_USER_MODEL  # e.g. "accounts.User"


# -----------------------------
# Company & Membership
# -----------------------------

class Company(models.Model):
    owner = models.ForeignKey(UserModelRef, on_delete=models.CASCADE, related_name="companies")
    name = models.CharField(max_length=200)
    logo = models.ImageField(upload_to="company_logos/", blank=True, null=True)
    address = models.TextField(blank=True)
    phone = models.CharField(max_length=50, blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    require_time_approval = models.BooleanField(default=False)

    class Meta:
        ordering = ("name", "id")

    def __str__(self) -> str:
        return self.name


class CompanyMember(models.Model):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    ROLE_CHOICES = [(OWNER, "Owner"), (ADMIN, "Admin"), (MEMBER, "Member")]

    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="members")
    user = models.ForeignKey(UserModelRef, on_delete=models.CASCADE, related_name="company_memberships")
    role = models.CharField(max_length=12, choices=ROLE_CHOICES, default=MEMBER)
    joined_at = models.DateTimeField(default=timezone.now)
    job_title = models.CharField(max_length=120, blank=True)
    hourly_rate = models.DecimalField(max_digits=9, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ("company", "user")
        ordering = ("-joined_at",)

    def __str__(self) -> str:
        return f"{self.company} — {self.user} ({self.role})"


class CompanyInvite(models.Model):
    PENDING = "pending"
    ACCEPTED = "accepted"
    CANCELED = "canceled"
    STATUS_CHOICES = [(PENDING, "Pending"), (ACCEPTED, "Accepted"), (CANCELED, "Canceled")]

    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="invites")
    email = models.EmailField()
    role = models.CharField(max_length=12, choices=CompanyMember.ROLE_CHOICES, default=CompanyMember.MEMBER)
    token = models.UUIDField(default=uuid4, unique=True, editable=False)
    invited_by = models.ForeignKey(
        UserModelRef,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_company_invites",
    )
    sent_at = models.DateTimeField(default=timezone.now)
    accepted_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=PENDING)

    class Meta:
        ordering = ("-sent_at",)

    def __str__(self) -> str:
        return f"Invite {self.email} → {self.company} ({self.role})"


# -----------------------------
# CRM: Client & Project
# -----------------------------

class Client(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="clients")
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100, blank=True)
    org = models.CharField("Company", max_length=200, blank=True)
    email = models.EmailField()
    phone = models.CharField(max_length=50, blank=True)
    address = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("org", "last_name", "first_name", "id")
        indexes = [
            models.Index(fields=["company", "org"]),
            models.Index(fields=["company", "email"]),
        ]

    def __str__(self) -> str:
        name = f"{(self.first_name or '').strip()} {(self.last_name or '').strip()}".strip()
        return self.org or name or self.email


class Project(models.Model):
    HOURLY = "hourly"
    FLAT = "flat"
    BILLING_TYPE_CHOICES = [(HOURLY, "Hourly"), (FLAT, "Flat Rate")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="projects")
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="projects")
    number = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=200)
    details = models.TextField(blank=True)
    billing_type = models.CharField(max_length=10, choices=BILLING_TYPE_CHOICES, default=HOURLY)
    budget = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    start_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)
    estimated_hours = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    team = models.ManyToManyField(UserModelRef, blank=True, related_name="team_projects")
    created_at = models.DateTimeField(default=timezone.now)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ("-created_at", "-id")
        indexes = [
            models.Index(fields=["company", "number"]),
            models.Index(fields=["company", "client", "due_date"]),
        ]

    def __str__(self) -> str:
        return f"{self.number} — {self.name}"

    def get_absolute_url(self) -> str:
        return reverse("core:project_detail", args=[self.pk])


# -----------------------------
# Billing: Invoices, Items, Payments, Expenses, Recurring
# -----------------------------

class Invoice(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    PAID = "paid"
    VOID = "void"
    STATUS_CHOICES = [(DRAFT, "Draft"), (SENT, "Sent"), (PAID, "Paid"), (VOID, "Void")]

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="invoices")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="invoices")
    number = models.CharField(max_length=30, unique=True)
    client = models.ForeignKey(Client, on_delete=models.PROTECT, related_name="invoices")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default=DRAFT)
    issue_date = models.DateField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    tax = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    public_token = models.UUIDField(default=uuid4, editable=False, unique=True)
    currency = models.CharField(max_length=3, default="usd")
    allow_reminders = models.BooleanField(default=True)
    reminder_log = models.CharField(
        max_length=120,
        blank=True,
        default="",
        help_text="CSV of offsets sent or 'manual' entries",
    )
    last_reminder_sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-issue_date", "-id")
        indexes = [models.Index(fields=["company", "status", "issue_date"])]

    def __str__(self) -> str:
        return f"Invoice {self.number}"

    def get_absolute_url(self) -> str:
        return reverse("core:invoice_detail", args=[self.pk])

    @property
    def balance(self) -> Decimal:
        return max((self.total or Decimal("0.00")) - (self.amount_paid or Decimal("0.00")), Decimal("0.00"))


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=9, decimal_places=2, default=Decimal("1.00"))
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ("id",)

    @property
    def line_total(self) -> Decimal:
        q = self.qty or Decimal("0.00")
        p = self.unit_price or Decimal("0.00")
        return (q * p).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return self.description


class Payment(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="payments")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    received_at = models.DateTimeField(default=timezone.now)
    method = models.CharField(max_length=50, blank=True)  # Stripe, Cash, Check, etc.
    external_id = models.CharField(max_length=200, blank=True, db_index=True)

    class Meta:
        ordering = ("-received_at", "-id")
        indexes = [models.Index(fields=["company", "invoice", "received_at"])]

    def __str__(self) -> str:
        return f"{self.amount} on {self.invoice}"


class Expense(models.Model):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="expenses")
    project = models.ForeignKey(Project, on_delete=models.SET_NULL, null=True, blank=True, related_name="expenses")
    vendor = models.CharField(max_length=200, blank=True)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    date = models.DateField(default=timezone.localdate)
    category = models.CharField(max_length=100, blank=True)
    is_billable = models.BooleanField(default=False)
    invoice = models.ForeignKey("Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="expenses")
    billable_markup_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percentage markup to apply when rebilling, e.g. 10.00 for 10%.",
    )
    billable_note = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ("-date", "-id")
        indexes = [models.Index(fields=["company", "project", "date"])]

    def __str__(self) -> str:
        return self.description


class RecurringPlan(models.Model):
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"
    FREQ_CHOICES = [(WEEKLY, "Weekly"), (MONTHLY, "Monthly"), (QUARTERLY, "Quarterly"), (YEARLY, "Yearly")]

    ACTIVE = "active"
    PAUSED = "paused"
    STATUS_CHOICES = [(ACTIVE, "Active"), (PAUSED, "Paused")]

    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="recurring_plans")
    client = models.ForeignKey("core.Client", on_delete=models.PROTECT)
    project = models.ForeignKey("core.Project", on_delete=models.SET_NULL, null=True, blank=True)
    template_invoice = models.ForeignKey(
        "core.Invoice",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Items/notes/tax copied each cycle.",
    )

    title = models.CharField(max_length=120)
    frequency = models.CharField(max_length=12, choices=FREQ_CHOICES, default=MONTHLY)
    start_date = models.DateField(help_text="First issue date.")
    next_run_date = models.DateField(help_text="Next scheduled generation date.")
    end_date = models.DateField(null=True, blank=True)
    due_days = models.PositiveIntegerField(default=14, help_text="Days after issue for due date.")

    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=ACTIVE)
    auto_email = models.BooleanField(default=True, help_text="Email the invoice automatically on generation.")
    max_occurrences = models.PositiveIntegerField(null=True, blank=True, help_text="Stop after N issues (optional).")
    occurrences_sent = models.PositiveIntegerField(default=0)
    last_run_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        return f"{self.title} · {self.get_frequency_display()}" # type: ignore

    def is_active(self) -> bool:
        if self.status != self.ACTIVE:
            return False
        if self.end_date and self.next_run_date and self.next_run_date > self.end_date:
            return False
        if self.max_occurrences is not None and self.occurrences_sent >= self.max_occurrences:
            return False
        return True


# -----------------------------
# Time Tracking
# -----------------------------

class TimeEntry(models.Model):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    STATUS_CHOICES = [(DRAFT, "Draft"), (SUBMITTED, "Submitted"), (APPROVED, "Approved"), (REJECTED, "Rejected")]

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="time_entries")
    user = models.ForeignKey(UserModelRef, on_delete=models.CASCADE, related_name="time_entries")
    started_at = models.DateTimeField(default=timezone.now)
    ended_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    hours = models.DecimalField(max_digits=7, decimal_places=2, default=Decimal("0.00"))
    is_billable = models.BooleanField(default=True)
    invoice = models.ForeignKey("Invoice", null=True, blank=True, on_delete=models.SET_NULL, related_name="time_entries")

    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=DRAFT)
    submitted_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="approved_timeentries",
    )
    reject_reason = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        ordering = ("-started_at", "-id")
        indexes = [
            models.Index(fields=["project", "user", "started_at"]),
            models.Index(fields=["project", "status", "started_at"]),
            models.Index(fields=["user", "status", "started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.project} — {self.user} — {self.hours}h ({self.status})"


# -----------------------------
# Estimates
# -----------------------------

class Estimate(models.Model):
    DRAFT = "draft"
    SENT = "sent"
    ACCEPTED = "accepted"
    DECLINED = "declined"
    EXPIRED = "expired"
    STATUS_CHOICES = [
        (DRAFT, "Draft"),
        (SENT, "Sent"),
        (ACCEPTED, "Accepted"),
        (DECLINED, "Declined"),
        (EXPIRED, "Expired"),
    ]

    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="estimates")
    client = models.ForeignKey("core.Client", on_delete=models.PROTECT, related_name="estimates")
    project = models.ForeignKey("core.Project", on_delete=models.SET_NULL, null=True, blank=True, related_name="estimates")

    number = models.CharField(max_length=32, db_index=True)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default=DRAFT)
    issue_date = models.DateField(default=timezone.now)
    valid_until = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    tax = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))

    is_template = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    public_token = models.UUIDField(default=uuid4, unique=True, editable=False)
    last_sent_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.CharField(max_length=120, blank=True, default="")
    declined_at = models.DateTimeField(null=True, blank=True)
    declined_by = models.CharField(max_length=120, blank=True, default="")
    client_note = models.TextField(blank=True, default="")

    converted_invoice = models.OneToOneField(
        "core.Invoice",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="from_estimate",
    )

    class Meta:
        unique_together = ("company", "number")
        ordering = ("-issue_date", "-id")
        indexes = [models.Index(fields=["company", "status", "issue_date"])]

    def __str__(self) -> str:
        return f"{self.number} — {self.client}"

    def get_absolute_url(self) -> str:
        return reverse("core:estimate_detail", args=[self.pk])

    def get_public_url(self) -> str:
        base = getattr(settings, "SITE_URL", "")
        return f"{base}{reverse('core:estimate_public', kwargs={'token': str(self.public_token)})}"


class EstimateItem(models.Model):
    estimate = models.ForeignKey(Estimate, on_delete=models.CASCADE, related_name="items")
    description = models.CharField(max_length=255)
    qty = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))
    unit_price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0.00"))

    class Meta:
        ordering = ("id",)

    @property
    def line_total(self) -> Decimal:
        q = self.qty or Decimal("0.00")
        p = self.unit_price or Decimal("0.00")
        return (q * p).quantize(Decimal("0.01"))

    def __str__(self) -> str:
        return self.description


# -----------------------------
# User Profile
# -----------------------------

class UserProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    phone = models.CharField(max_length=40, blank=True)
    title = models.CharField(max_length=120, blank=True)
    timezone = models.CharField(max_length=64, blank=True, default="")
    locale = models.CharField(max_length=16, blank=True, default="")
    bio = models.TextField(blank=True)
    dark_mode = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("user",)

    def __str__(self) -> str:
        # be defensive: custom users may not implement get_full_name
        name = getattr(self.user, "get_full_name", lambda: "")() or getattr(self.user, "get_username", lambda: "")()
        return name or str(self.user)


# -----------------------------
# Notifications
# -----------------------------

class NotificationQuerySet(models.QuerySet):
    def for_company_user(self, company, user):
        if not company or not getattr(user, "is_authenticated", False):
            return self.none()
        return self.filter(company=company, recipient=user)

    def unread(self):
        return self.filter(read_at__isnull=True)

    def read(self):
        return self.filter(read_at__isnull=False)


class Notification(models.Model):
    GENERIC = "generic"
    INVOICE_CREATED = "invoice_created"
    INVOICE_PAID = "invoice_paid"
    ESTIMATE_ACCEPTED = "estimate_accepted"
    ESTIMATE_CREATED = "estimate_created"
    ESTIMATE_CONVERTED = "estimate_converted"
    PROJECT_CREATED = "project_created"
    TIME_ADDED = "time_added"
    EXPENSE_ADDED = "expense_added"

    KIND_CHOICES = [
        (GENERIC, "Generic"),
        (INVOICE_CREATED, "Invoice created"),
        (INVOICE_PAID, "Invoice paid"),
        (ESTIMATE_ACCEPTED, "Estimate accepted"),
        (ESTIMATE_CREATED, "Estimate created"),
        (ESTIMATE_CONVERTED, "Estimate converted"),
        (PROJECT_CREATED, "Project created"),
        (TIME_ADDED, "Time added"),
        (EXPENSE_ADDED, "Expense added"),
    ]

    company = models.ForeignKey("core.Company", on_delete=models.CASCADE, related_name="notifications")
    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications_sent"
    )

    kind = models.CharField(max_length=40, choices=KIND_CHOICES, default=GENERIC)
    text = models.CharField(max_length=280)
    url = models.CharField(max_length=500, blank=True, default="")

    target_content_type = models.ForeignKey(ContentType, on_delete=models.SET_NULL, null=True, blank=True)
    target_object_id = models.PositiveIntegerField(null=True, blank=True)
    target = GenericForeignKey("target_content_type", "target_object_id")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)

    objects = NotificationQuerySet.as_manager()

    class Meta:
        ordering = ("-created_at",)
        indexes = [
            models.Index(fields=["company", "recipient", "read_at", "created_at"]),
            models.Index(fields=["recipient", "read_at", "created_at"]),
            models.Index(fields=["target_content_type", "target_object_id"]),
        ]

    @property
    def is_read(self) -> bool:
        return bool(self.read_at)

    def mark_read(self, *, save: bool = True):
        if not self.read_at:
            self.read_at = timezone.now()
            if save:
                self.save(update_fields=["read_at"])

    def link(self) -> str:
        if self.url:
            return self.url
        if self.target and hasattr(self.target, "get_absolute_url"):
            try:
                return self.target.get_absolute_url()  # type: ignore[no-any-return]
            except Exception:
                pass
        return ""

    def __str__(self) -> str:
        who = getattr(self.recipient, "email", str(self.recipient))
        return f"{who} · {self.text}"


# -----------------------------
# Suggestions / Feedback
# -----------------------------

class Suggestion(models.Model):
    STATUS_NEW = "new"
    STATUS_REVIEWED = "reviewed"
    STATUS_CLOSED = "closed"
    STATUS_CHOICES = [
        (STATUS_NEW, "New"),
        (STATUS_REVIEWED, "Reviewed"),
        (STATUS_CLOSED, "Closed"),
    ]

    company = models.ForeignKey(
        "core.Company", null=True, blank=True, on_delete=models.SET_NULL, related_name="suggestions"
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="suggestions"
    )
    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField(blank=True)
    subject = models.CharField(max_length=200)
    message = models.TextField()
    page_url = models.CharField(max_length=300, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    class Meta:
        ordering = ("-created_at",)

    def __str__(self) -> str:
        who = self.name or self.email or (getattr(self.user, "email", "") or "Anon")
        return f"{who} — {self.subject[:60]}"
