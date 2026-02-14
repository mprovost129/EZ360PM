# documents/models.py
from __future__ import annotations

from django.db import models
from django.db.models import Q
from django.core.exceptions import ValidationError


from core.models import SyncModel
from companies.models import Company, EmployeeProfile
from crm.models import Client
from catalog.models import CatalogItem
from projects.models import Project


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
    
    def _enforce_invoice_immutability(self, previous: "Document") -> None:
        # Phase 3A (proper): Invoice immutability + status downgrade protection
        if self.doc_type != DocumentType.INVOICE:
            return

        # Status downgrade protections
        downgrade_block = {
            DocumentStatus.SENT: {DocumentStatus.DRAFT},
            DocumentStatus.PARTIALLY_PAID: {DocumentStatus.DRAFT, DocumentStatus.SENT},
            DocumentStatus.PAID: {DocumentStatus.DRAFT, DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID},
        }
        if previous.status in downgrade_block and self.status in downgrade_block[previous.status]:
            raise ValidationError("Invoice status downgrade is not allowed.")

        # Sent or beyond: lock money fields
        locked_statuses = {DocumentStatus.SENT, DocumentStatus.PARTIALLY_PAID, DocumentStatus.PAID}
        if previous.status in locked_statuses:
            if (
                previous.subtotal_cents != self.subtotal_cents
                or previous.tax_cents != self.tax_cents
                or previous.total_cents != self.total_cents
            ):
                raise ValidationError("Invoice financial fields cannot be modified once sent.")

        # Paid: fully immutable (no status changes)
        if previous.status == DocumentStatus.PAID and self.status != DocumentStatus.PAID:
            raise ValidationError("Paid invoices cannot change status.")

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
