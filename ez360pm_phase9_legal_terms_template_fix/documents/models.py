# documents/models.py
from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError
from django.utils import timezone

from decimal import Decimal


class InvoiceLockedError(ValidationError):
    """Raised when attempting to mutate a locked invoice."""


from core.models import SyncModel
from companies.models import Company, EmployeeProfile
from crm.models import Client
from catalog.models import CatalogItem
from projects.models import Project
import uuid


class DocumentType(models.TextChoices):
    INVOICE = "invoice", "Invoice"
    ESTIMATE = "estimate", "Estimate"
    PROPOSAL = "proposal", "Proposal"


class DocumentStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SENT = "sent", "Sent"
    ACCEPTED = "accepted", "Accepted"       # estimates/proposals
    DECLINED = "declined", "Declined"       # estimates/proposals
    PARTIALLY_PAID = "partially_paid", "Partially Paid"  # invoices
    PAID = "paid", "Paid"                   # invoices
    VOID = "void", "Void"


class DocumentTemplate(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="document_templates")
    doc_type = models.CharField(max_length=20, choices=DocumentType.choices)
    name = models.CharField(max_length=160)

    header_text = models.TextField(blank=True, default="")
    footer_text = models.TextField(blank=True, default="")
    notes_default = models.TextField(blank=True, default="")

    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "doc_type", "name"], name="uniq_company_template_type_name"),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} · {self.doc_type} · {self.name}"


class NumberingScheme(SyncModel):
    """
    Per-company flexible numbering formats.
    Example patterns:
      - "INV-{YYYY}-{SEQ:4}"
      - "{YY}/{MM}/{SEQ:3}"
      - "{SEQ:5}"
    """

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="numbering_scheme")

    invoice_pattern = models.CharField(max_length=80, default="{YY}/{MM}/{SEQ:3}")
    estimate_pattern = models.CharField(max_length=80, default="{YY}/{MM}/{SEQ:3}")
    proposal_pattern = models.CharField(max_length=80, default="{YY}/{MM}/{SEQ:3}")

    invoice_seq = models.BigIntegerField(default=1)
    estimate_seq = models.BigIntegerField(default=1)
    proposal_seq = models.BigIntegerField(default=1)

    def __str__(self) -> str:
        return f"{self.company.name} · Numbering"


class Document(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=20, choices=DocumentType.choices)

    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="documents")

    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_documents")

    number = models.CharField(max_length=40, blank=True, default="")  # allocated via numbering scheme
    title = models.CharField(max_length=200, blank=True, default="")
    description = models.TextField(blank=True, default="")

    issue_date = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)  # invoice
    valid_until = models.DateField(null=True, blank=True)  # proposal/estimate

    status = models.CharField(max_length=30, choices=DocumentStatus.choices, default=DocumentStatus.DRAFT)

    subtotal_cents = models.BigIntegerField(default=0)
    tax_cents = models.BigIntegerField(default=0)
    total_cents = models.BigIntegerField(default=0)

    # payments snapshot for invoices
    amount_paid_cents = models.BigIntegerField(default=0)
    balance_due_cents = models.BigIntegerField(default=0)

    notes = models.TextField(blank=True, default="")

    # Optional free-text blocks typically populated from a DocumentTemplate at creation.
    # These are rendered in the customer-facing output and editable in the composer.
    header_text = models.TextField(blank=True, default="")
    footer_text = models.TextField(blank=True, default="")

    # ------------------------------------------------------------------
    # Phase 9 – Document Composer (paper-style editor)
    # ------------------------------------------------------------------
    sales_tax_percent = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        default=Decimal("0.000"),
        help_text="Sales tax percentage used for real-time totals and PDF display.",
    )

    class DepositType(models.TextChoices):
        NONE = "none", "None"
        PERCENT = "percent", "Percent"
        FIXED = "fixed", "Fixed"

    deposit_type = models.CharField(
        max_length=10,
        choices=DepositType.choices,
        default=DepositType.NONE,
    )
    deposit_value = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Percent (e.g., 25.00) or fixed amount (dollars) depending on deposit_type.",
    )
    deposit_cents = models.BigIntegerField(
        default=0,
        help_text="Computed deposit requested in cents at time of last save.",
    )

    terms = models.TextField(
        blank=True,
        default="",
        help_text="Invoice terms shown on customer-facing document.",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "doc_type", "status"]),
            models.Index(fields=["company", "updated_at"]),
            models.Index(fields=["company", "number"]),
            # Phase 3W: list pages are driven by company+doc_type and ordered by created_at.
            # Use a partial index to ignore soft-deleted rows.
            models.Index(
                fields=["company", "doc_type", "created_at"],
                name="co_type_create_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["company", "doc_type", "status", "created_at"],
                name="co_type_status_create_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self) -> str:
        num = self.number or "(unassigned)"
        return f"{self.company.name} · {self.doc_type} · {num}"


    def credit_applied_cents(self) -> int:
        """Sum of posted credit notes applied to A/R for this invoice."""
        if self.doc_type != DocumentType.INVOICE:
            return 0
        from django.db.models import Sum
        from documents.models import CreditNote, CreditNoteStatus  # local import

        agg = (
            CreditNote.objects.filter(invoice=self, status=CreditNoteStatus.POSTED, deleted_at__isnull=True)
            .aggregate(total=Sum("ar_applied_cents"))
        )
        return int(agg.get("total") or 0)

    
    def credit_applications_cents(self) -> int:
        """Sum of applied client credits (from credit ledger applications) for this invoice."""
        if self.doc_type != DocumentType.INVOICE:
            return 0
        from django.db.models import Sum
        from payments.models import ClientCreditApplication  # local import

        agg = (
            ClientCreditApplication.objects.filter(invoice=self, deleted_at__isnull=True)
            .aggregate(total=Sum("cents"))
        )
        return int(agg.get("total") or 0)

    def balance_due_effective_cents(self) -> int:
            """Balance due including posted credit notes. Does not mutate stored fields."""
            if self.doc_type != DocumentType.INVOICE:
                return int(self.balance_due_cents or 0)
            total = int(self.total_cents or 0)
            paid = int(self.amount_paid_cents or 0)
            credit = int(self.credit_applied_cents() or 0)
            credit_apps = int(self.credit_applications_cents() or 0)
            return max(0, total - paid - credit - credit_apps)

    @property
    def is_locked(self) -> bool:
        """True if this document should be treated as immutable (money fields / line items)."""
        return self.is_invoice_locked()

    def invoice_lock_reason(self) -> str:
        if self.doc_type != DocumentType.INVOICE:
            return ""
        if self.status in {DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID, DocumentStatus.PAID}:
            return f"status={self.status}"
        try:
            from payments.models import Payment, PaymentStatus, ClientCreditApplication

            if Payment.objects.filter(invoice=self, status__in=[PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED]).exists():
                return "payments_applied"
            if ClientCreditApplication.objects.filter(invoice=self, deleted_at__isnull=True).exists():
                return "client_credit_applied"
        except Exception:
            pass
        try:
            if CreditNote.objects.filter(invoice=self, status=CreditNoteStatus.POSTED, deleted_at__isnull=True).exists():
                return "credit_note_posted"
        except Exception:
            pass
        return ""

    def is_invoice_locked(self) -> bool:
        """Invoice is locked if any money-affecting event has occurred."""
        if self.doc_type != DocumentType.INVOICE:
            return False

        if self.status in {DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID, DocumentStatus.PAID}:
            return True

        # Lock on applied payments / credits even if status hasn't caught up yet.
        try:
            from payments.models import Payment, PaymentStatus, ClientCreditApplication

            if Payment.objects.filter(invoice=self, status__in=[PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED]).exists():
                return True
            if ClientCreditApplication.objects.filter(invoice=self, deleted_at__isnull=True).exists():
                return True
        except Exception:
            # Best-effort: don't block system startup if payments app is unavailable during migrations.
            pass

        try:
            if CreditNote.objects.filter(invoice=self, status=CreditNoteStatus.POSTED, deleted_at__isnull=True).exists():
                return True
        except Exception:
            pass

        return False

    def _enforce_invoice_immutability(self, previous: "Document") -> None:
        """Hard guardrails around invoice mutation."""
        if self.doc_type != DocumentType.INVOICE:
            return

        # Status downgrade protections
        downgrade_block = {
            DocumentStatus.SENT: {DocumentStatus.DRAFT},
            DocumentStatus.PARTIALLY_PAID: {DocumentStatus.DRAFT, DocumentStatus.SENT},
            DocumentStatus.PAID: {DocumentStatus.DRAFT, DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID},
        }
        if previous.status in downgrade_block and self.status in downgrade_block[previous.status]:
            raise InvoiceLockedError("Invoice status downgrade is not allowed.")

        # Paid: fully immutable (no status changes)
        if previous.status == DocumentStatus.PAID and self.status != DocumentStatus.PAID:
            raise InvoiceLockedError("Paid invoices cannot change status.")

        try:
            locked_before = previous.is_invoice_locked()
        except Exception:
            locked_before = previous.status in {DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID, DocumentStatus.PAID}

        if locked_before:
            immutable_fields = [
                ("client_id", previous.client_id, self.client_id),
                ("project_id", previous.project_id, self.project_id),
                ("issue_date", previous.issue_date, self.issue_date),
                ("due_date", previous.due_date, self.due_date),
                ("valid_until", previous.valid_until, self.valid_until),
                ("subtotal_cents", previous.subtotal_cents, self.subtotal_cents),
                ("tax_cents", previous.tax_cents, self.tax_cents),
                ("total_cents", previous.total_cents, self.total_cents),
            ]
            changed = [name for (name, a, b) in immutable_fields if a != b]
            if changed:
                raise InvoiceLockedError(f"Invoice is locked and cannot be modified ({', '.join(changed)}).")


    def save(self, *args, **kwargs):
        # Enforce invariants even outside ModelForms/admin.
        if self.pk:
            previous = Document.objects.filter(pk=self.pk).first()
            if previous:
                self._enforce_invoice_immutability(previous)
        super().save(*args, **kwargs)


class DocumentLineItem(SyncModel):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="line_items")
    sort_order = models.PositiveIntegerField(default=0)

    catalog_item = models.ForeignKey(CatalogItem, null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price_cents = models.BigIntegerField(default=0)
    line_subtotal_cents = models.BigIntegerField(default=0)
    tax_cents = models.BigIntegerField(default=0)
    line_total_cents = models.BigIntegerField(default=0)

    is_taxable = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["document", "sort_order"])]


    def _assert_document_unlocked(self) -> None:
        # Only invoices are locked; estimates/proposals can be edited.
        try:
            if self.document and self.document.is_invoice_locked():
                raise InvoiceLockedError("Invoice line items cannot be modified once the invoice is locked.")
        except InvoiceLockedError:
            raise
        except Exception:
            # Best-effort: do not break migrations.
            return

    def save(self, *args, **kwargs):
        self._assert_document_unlocked()
        return super().save(*args, **kwargs)

    def soft_delete(self, *, save: bool = True):
        self._assert_document_unlocked()
        return super().soft_delete(save=save)

    def delete(self, using=None, keep_parents=False, *, hard: bool = False):
        self._assert_document_unlocked()
        return super().delete(using=using, keep_parents=keep_parents, hard=hard)

    
    def clean(self):
        super().clean()
        if (
            self.document.doc_type == DocumentType.INVOICE
            and self.document.status != DocumentStatus.DRAFT
        ):
            raise ValidationError("Cannot modify invoice line items once the invoice is sent.")

    def __str__(self) -> str:
        return f"{self.document_id} · {self.name}"


class RecurringFrequency(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    WEEKLY = "weekly", "Weekly"


class RecurringPlan(SyncModel):
    """Recurring invoice plan.

    v1 goals:
    - Create invoices on a schedule (monthly/weekly)
    - Copy line items from plan to the invoice
    - Allocate invoice number using the company numbering scheme
    - Update next_run_date after successful generation
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="recurring_plans")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="recurring_plans")
    project = models.ForeignKey(Project, null=True, blank=True, on_delete=models.SET_NULL, related_name="recurring_plans")
    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_recurring_plans")

    name = models.CharField(max_length=160)
    is_active = models.BooleanField(default=True)

    frequency = models.CharField(max_length=20, choices=RecurringFrequency.choices, default=RecurringFrequency.MONTHLY)
    interval = models.PositiveIntegerField(default=1, help_text="Every N months/weeks.")

    # Monthly scheduling
    day_of_month = models.PositiveIntegerField(
        default=1,
        help_text="For monthly plans: day of month to create invoices (1-28 recommended).",
    )

    next_run_date = models.DateField(help_text="Next date this plan should generate an invoice.")
    last_run_date = models.DateField(null=True, blank=True)

    due_days = models.PositiveIntegerField(default=15, help_text="Invoice due date will be issue_date + due_days.")

    auto_mark_sent = models.BooleanField(
        default=True,
        help_text="If enabled, generated invoices are marked as SENT (ready to email / collect payment).",
    )

    auto_email = models.BooleanField(
        default=False,
        help_text="If enabled, generated invoices are emailed to the client automatically.",
    )
    email_to_override = models.EmailField(
        blank=True,
        default="",
        help_text="Optional override recipient (leave blank to use the client's email).",
    )

    notes = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["company", "is_active", "next_run_date"]),
            models.Index(fields=["company", "updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} · Recurring · {self.name}"


class RecurringPlanLineItem(SyncModel):
    plan = models.ForeignKey(RecurringPlan, on_delete=models.CASCADE, related_name="line_items")
    sort_order = models.PositiveIntegerField(default=0)

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")

    qty = models.DecimalField(max_digits=12, decimal_places=2, default=1)
    unit_price_cents = models.BigIntegerField(default=0)
    is_taxable = models.BooleanField(default=False)

    class Meta:
        indexes = [models.Index(fields=["plan", "sort_order"])]

    def __str__(self) -> str:
        return f"{self.plan_id} · {self.name}"


class CreditNoteStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    POSTED = "posted", "Posted"


class CreditNote(SyncModel):
    """A corrective financial document that reduces an invoice balance.

    Draft → Posted workflow. Posting is additive and creates a new JournalEntry.
    Invoice status remains unchanged by credit notes.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="credit_notes")
    invoice = models.ForeignKey(Document, on_delete=models.PROTECT, related_name="credit_notes")

    created_by = models.ForeignKey(
        EmployeeProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="created_credit_notes",
    )

    number = models.CharField(max_length=40, blank=True, default="")
    status = models.CharField(max_length=20, choices=CreditNoteStatus.choices, default=CreditNoteStatus.DRAFT)

    subtotal_cents = models.BigIntegerField(default=0)
    tax_cents = models.BigIntegerField(default=0)
    total_cents = models.BigIntegerField(default=0)

    # Allocation (set when posted)
    ar_applied_cents = models.BigIntegerField(default=0)
    customer_credit_cents = models.BigIntegerField(default=0)

    reason = models.TextField(blank=True, default="")

    posted_at = models.DateTimeField(null=True, blank=True)
    journal_entry = models.ForeignKey(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="credit_notes",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["company", "created_at"]),
            models.Index(fields=["invoice"]),
        ]

    def clean(self):
        super().clean()
        if self.total_cents <= 0:
            raise ValidationError("Credit note total must be greater than zero.")
        if self.invoice_id:
            if self.invoice.doc_type != DocumentType.INVOICE:
                raise ValidationError("Credit notes can only be applied to invoices.")
            if self.invoice.status == DocumentStatus.VOID:
                raise ValidationError("Cannot apply a credit note to a void invoice.")
            if self.invoice.company_id != self.company_id:
                raise ValidationError("Credit note company must match the invoice company.")

    def __str__(self) -> str:
        num = self.number or "(unassigned)"
        return f"{self.company.name} · credit_note · {num}"



class CreditNoteNumberSequence(models.Model):
    """Per-company sequence for credit note numbering."""
    company = models.OneToOneField("companies.Company", on_delete=models.CASCADE, related_name="credit_note_sequence")
    next_number = models.PositiveIntegerField(default=1)

    def __str__(self) -> str:
        return f"CreditNoteSequence({self.company_id})={self.next_number}"

class ClientStatementRecipientPreference(models.Model):
    """Stores per-company, per-client statement email defaults.

    Phase 7H35: speed up collections workflows by remembering the last-used
    statement recipient for a client.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="statement_recipient_prefs")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="statement_recipient_prefs")

    last_to_email = models.EmailField(blank=True, default="")

    updated_at = models.DateTimeField(default=timezone.now)
    updated_by = models.ForeignKey(
        "accounts.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="statement_recipient_prefs_updated",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "client"], name="uniq_company_client_stmt_recipient"),
        ]
        indexes = [
            models.Index(fields=["company", "updated_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} · {self.client.display_label()} · {self.last_to_email or '(none)'}"





class ClientStatementActivity(SyncModel):
    """Per-client statement activity for collections workflows.

    Phase 7H44:
    - Track last viewed statement page.
    - Track last emailed statement (manual send or reminder send).

    Used for lightweight CRM context on the client detail page.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="client_statement_activity")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="statement_activity")

    last_viewed_at = models.DateTimeField(null=True, blank=True)
    last_viewed_by = models.ForeignKey(
        EmployeeProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="viewed_statement_activity",
    )

    last_sent_at = models.DateTimeField(null=True, blank=True)
    last_sent_to = models.EmailField(blank=True, default="")
    last_sent_by = models.ForeignKey(
        EmployeeProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="sent_statement_activity",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "client"], name="doc_stmt_activity_company_client_uniq"),
        ]
        indexes = [
            models.Index(fields=["company", "last_viewed_at"], name="doc_stmtact_company_viewed_idx"),
            models.Index(fields=["company", "last_sent_at"], name="doc_stmtact_company_sent_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} · {self.client.display_label()}"


class CollectionsNoteStatus(models.TextChoices):
    OPEN = "open", "Open"
    DONE = "done", "Done"


class ClientCollectionsNote(SyncModel):
    """Lightweight collections notes + follow-up tasks per client.

    Phase 7H46:
    - Allow staff to log collections notes directly from the Client Statement page.
    - Support optional follow-up date to act as a simple task/reminder.
    - Support completing (mark done) without deletion.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="collections_notes")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="collections_notes")

    note = models.TextField(blank=False)
    follow_up_on = models.DateField(null=True, blank=True, db_index=True)

    status = models.CharField(max_length=12, choices=CollectionsNoteStatus.choices, default=CollectionsNoteStatus.OPEN, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        EmployeeProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="completed_collections_notes",
    )

    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_collections_notes")

    class Meta:
        ordering = ["status", "-created_at"]
        indexes = [
            models.Index(fields=["company", "client", "status"], name="doc_colnote_co_client_stat_idx"),
            models.Index(fields=["company", "status", "follow_up_on"], name="doc_colnote_co_stat_due_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} · {self.client.display_label()} · {self.status}"

class StatementReminderTone(models.TextChoices):
    FRIENDLY = "friendly", "Friendly nudge"
    PAST_DUE = "past_due", "Past due"


class StatementReminderStatus(models.TextChoices):
    SCHEDULED = "scheduled", "Scheduled"
    SENT = "sent", "Sent"
    CANCELED = "canceled", "Canceled"
    FAILED = "failed", "Failed"


class StatementReminder(SyncModel):
    """A lightweight scheduling hook for statement reminder emails.

    Staff schedule reminders; a periodic management command sends due reminders.
    """

    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="statement_reminders")
    client = models.ForeignKey(Client, on_delete=models.CASCADE, related_name="statement_reminders")

    scheduled_for = models.DateField(db_index=True)
    recipient_email = models.EmailField(blank=True, default="")

    date_from = models.DateField(null=True, blank=True)
    date_to = models.DateField(null=True, blank=True)
    attach_pdf = models.BooleanField(default=False)

    tone = models.CharField(max_length=16, choices=StatementReminderTone.choices, default=StatementReminderTone.FRIENDLY, db_index=True)

    status = models.CharField(max_length=16, choices=StatementReminderStatus.choices, default=StatementReminderStatus.SCHEDULED, db_index=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    attempted_at = models.DateTimeField(null=True, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    created_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="created_statement_reminders")

    # Audit trail: who last modified the reminder (reschedule/cancel edits).
    modified_by = models.ForeignKey(
        EmployeeProfile,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="modified_statement_reminders",
    )

    class Meta:
        ordering = ["-scheduled_for", "-created_at"]
        indexes = [
            models.Index(fields=["company", "status", "scheduled_for"], name="doc_stmtrem_co_stat_sched"),
            models.Index(fields=["client", "status", "scheduled_for"], name="doc_stmtrem_cl_stat_sched"),
        ]

    def __str__(self) -> str:
        return f"{self.company.name} · {self.client.display_label()} · {self.scheduled_for} ({self.status})"
