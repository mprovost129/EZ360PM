from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from documents.models import Document, DocumentType, DocumentStatus
from payments.models import Payment, PaymentStatus
from expenses.models import Expense, ExpenseStatus
from companies.models import Company
from crm.models import Client
from projects.models import Project

from .models import (
    JournalEntry,
    JournalLine,
    DefaultAccountCodes,
    get_account,
)


CODES = DefaultAccountCodes()


def _create_entry(
    *,
    company: Company,
    source_type: str,
    source_id,
    entry_date,
    memo: str,
    created_by=None,
) -> JournalEntry:
    entry, _ = JournalEntry.objects.get_or_create(
        company=company,
        source_type=source_type,
        source_id=source_id,
        defaults={
            "entry_date": entry_date,
            "memo": memo[:240],
            "created_by": created_by,
        },
    )
    return entry


def _replace_lines(entry: JournalEntry, lines: list[dict]) -> None:
    """Create the journal lines once.

    Hardening rule: journal entries are immutable once posted.
    We treat "has any lines" as "posted".
    """
    if entry.lines.exists():
        return

    debit_total = sum(int(l.get("debit_cents") or 0) for l in lines)
    credit_total = sum(int(l.get("credit_cents") or 0) for l in lines)
    if debit_total != credit_total:
        raise ValueError("Unbalanced journal entry (debits must equal credits).")

    for l in lines:
        JournalLine.objects.create(
            entry=entry,
            account=l["account"],
            description=l.get("description", "")[:240],
            debit_cents=int(l.get("debit_cents") or 0),
            credit_cents=int(l.get("credit_cents") or 0),
            client=l.get("client"),
            project=l.get("project"),
        )


@transaction.atomic
def post_invoice_if_needed(invoice: Document) -> JournalEntry | None:
    if invoice.doc_type != DocumentType.INVOICE:
        return None
    if invoice.status == DocumentStatus.DRAFT or invoice.status == DocumentStatus.VOID:
        return None
    if invoice.deleted_at:
        return None

    company = invoice.company
    ar = get_account(company, CODES.AR)
    revenue = get_account(company, CODES.REVENUE)
    sales_tax = get_account(company, CODES.SALES_TAX_PAYABLE)

    subtotal = int(invoice.subtotal_cents or 0)
    tax = int(invoice.tax_cents or 0)
    total = int(invoice.total_cents or 0)

    if total <= 0:
        return None

    entry = _create_entry(
        company=company,
        source_type="invoice",
        source_id=invoice.id,
        entry_date=invoice.issue_date or timezone.localdate(),
        memo=f"Invoice {invoice.number or str(invoice.id)[:8]}",
        created_by=getattr(invoice, "created_by_user", None),
    )

    # Phase 3A (proper): Once invoice journal is posted, do not mutate lines.
    if entry.lines.exists():
        return entry

    lines = [
        {
            "account": ar,
            "description": "Accounts Receivable",
            "debit_cents": total,
            "credit_cents": 0,
            "client": invoice.client,
            "project": getattr(invoice, "project", None),
        },
        {
            "account": revenue,
            "description": "Revenue",
            "debit_cents": 0,
            "credit_cents": subtotal,
            "client": invoice.client,
            "project": getattr(invoice, "project", None),
        },
    ]
    if tax:
        lines.append(
            {
                "account": sales_tax,
                "description": "Sales Tax Payable",
                "debit_cents": 0,
                "credit_cents": tax,
                "client": invoice.client,
                "project": getattr(invoice, "project", None),
            }
        )

    _replace_lines(entry, lines)
    return entry


@transaction.atomic
def post_payment_if_needed(payment: Payment) -> JournalEntry | None:
    if payment.status != PaymentStatus.SUCCEEDED:
        return None
    if payment.deleted_at:
        return None
    if not payment.amount_cents or int(payment.amount_cents) <= 0:
        return None

    company = payment.company
    cash = get_account(company, CODES.CASH)
    ar = get_account(company, CODES.AR)
    credits = get_account(company, CODES.CUSTOMER_CREDITS)

    amount = int(payment.amount_cents or 0)

    # Determine how much of this payment actually reduces AR
    ar_credit = amount
    credit_liability = 0
    invoice = payment.invoice
    if invoice and invoice.doc_type == DocumentType.INVOICE and not invoice.deleted_at:
        # Use the invoice balance due AFTER applying the payment is tricky; we estimate by
        # using total - (amount_paid - this payment) = prior balance.
        try:
            prior_paid = int(invoice.amount_paid_cents or 0) - amount
            prior_paid = max(prior_paid, 0)
            prior_balance = max(int(invoice.total_cents or 0) - prior_paid, 0)
            ar_credit = min(amount, prior_balance)
            credit_liability = max(amount - ar_credit, 0)
        except Exception:
            ar_credit = amount

    entry = _create_entry(
        company=company,
        source_type="payment",
        source_id=payment.id,
        entry_date=payment.payment_date or timezone.localdate(),
        memo=f"Payment {str(payment.id)[:8]}",
        created_by=getattr(payment, "created_by_user", None),
    )

    lines = [
        {
            "account": cash,
            "description": "Cash",
            "debit_cents": amount,
            "credit_cents": 0,
            "client": payment.client or (invoice.client if invoice else None),
            "project": getattr(invoice, "project", None) if invoice else None,
        },
        {
            "account": ar,
            "description": "Accounts Receivable",
            "debit_cents": 0,
            "credit_cents": ar_credit,
            "client": payment.client or (invoice.client if invoice else None),
            "project": getattr(invoice, "project", None) if invoice else None,
        },
    ]
    if credit_liability:
        lines.append(
            {
                "account": credits,
                "description": "Customer Credits",
                "debit_cents": 0,
                "credit_cents": credit_liability,
                "client": payment.client or (invoice.client if invoice else None),
                "project": getattr(invoice, "project", None) if invoice else None,
            }
        )

    _replace_lines(entry, lines)
    return entry


@transaction.atomic

def post_payment_refund_if_needed(refund) -> JournalEntry | None:
    from payments.models import PaymentRefundStatus, PaymentRefund
    if refund.status != PaymentRefundStatus.SUCCEEDED:
        return None
    if refund.deleted_at:
        return None
    if not refund.cents or int(refund.cents) <= 0:
        return None

    company = refund.company
    cash = get_account(company, CODES.CASH)
    ar = get_account(company, CODES.AR)
    credits = get_account(company, CODES.CUSTOMER_CREDITS)

    amount = int(refund.cents or 0)
    payment = refund.payment
    invoice = getattr(payment, "invoice", None)

    # Look up the original payment journal entry to determine allocation between AR and Customer Credits.
    ar_part = amount
    credits_part = 0
    try:
        orig = JournalEntry.objects.filter(company=company, source_type="payment", source_id=payment.id).first()
        if orig:
            ar_credited = int(orig.lines.filter(account=ar).aggregate(total=Sum("credit_cents")).get("total") or 0)
            credits_credited = int(orig.lines.filter(account=credits).aggregate(total=Sum("credit_cents")).get("total") or 0)
            base = max(ar_credited + credits_credited, 0)
            if base > 0:
                # Pro-rate refund to match original allocation.
                ar_part = (amount * ar_credited) // base
                ar_part = min(ar_part, amount)
                credits_part = amount - ar_part
    except Exception:
        ar_part = amount
        credits_part = 0

    entry = _create_entry(
        company=company,
        source_type="payment_refund",
        source_id=refund.id,
        entry_date=timezone.localdate(),
        memo=f"Refund {str(refund.id)[:8]}",
        created_by=getattr(refund, "created_by_user", None),
    )

    client_obj = getattr(payment, "client", None) or (invoice.client if invoice else None)

    lines = [
        {
            "account": cash,
            "description": "Cash",
            "debit_cents": 0,
            "credit_cents": amount,
            "client": client_obj,
            "project": getattr(invoice, "project", None) if invoice else None,
        },
        {
            "account": ar,
            "description": "Accounts Receivable",
            "debit_cents": ar_part,
            "credit_cents": 0,
            "client": client_obj,
            "project": getattr(invoice, "project", None) if invoice else None,
        },
    ]
    if credits_part:
        lines.append(
            {
                "account": credits,
                "description": "Customer Credits",
                "debit_cents": credits_part,
                "credit_cents": 0,
                "client": client_obj,
                "project": getattr(invoice, "project", None) if invoice else None,
            }
        )

    _replace_lines(entry, lines)
    return entry



def post_expense_if_needed(expense: Expense) -> JournalEntry | None:
    if expense.status in {ExpenseStatus.VOID, ExpenseStatus.DRAFT}:
        return None
    if expense.deleted_at:
        return None
    total = int(expense.total_cents or 0)
    if total <= 0:
        return None

    company = expense.company
    expenses_acc = get_account(company, CODES.EXPENSES)
    cash = get_account(company, CODES.CASH)

    entry = _create_entry(
        company=company,
        source_type="expense",
        source_id=expense.id,
        entry_date=expense.date or timezone.localdate(),
        memo=f"Expense {(expense.merchant.name if expense.merchant else '')}".strip()[:240] or f"Expense {str(expense.id)[:8]}",
        created_by=getattr(expense, "created_by_user", None),
    )

    lines = [
        {
            "account": expenses_acc,
            "description": expense.description or "Expense",
            "debit_cents": total,
            "credit_cents": 0,
            "client": getattr(expense, "client", None),
            "project": getattr(expense, "project", None),
        },
        {
            "account": cash,
            "description": "Cash",
            "debit_cents": 0,
            "credit_cents": total,
            "client": getattr(expense, "client", None),
            "project": getattr(expense, "project", None),
        },
    ]
    _replace_lines(entry, lines)
    return entry

@transaction.atomic
def post_credit_note_if_needed(credit_note) -> JournalEntry | None:
    """Post a credit note (Draft -> Posted) by creating an immutable reversing JournalEntry.

    - Additive only: never mutates existing journal entries.
    - Invoice status remains unchanged by credit notes.
    - If the linked invoice is already fully paid, excess credit is posted to Customer Credits (liability).
    """
    from documents.models import CreditNoteStatus  # local import to avoid cycles
    from audit.services import log_event

    if credit_note.deleted_at:
        return None
    if credit_note.status != CreditNoteStatus.DRAFT:
        return credit_note.journal_entry

    invoice = credit_note.invoice
    if not invoice or invoice.deleted_at:
        return None
    if invoice.doc_type != DocumentType.INVOICE or invoice.status == DocumentStatus.VOID:
        return None

    company = credit_note.company

    ar = get_account(company, CODES.AR)
    revenue = get_account(company, CODES.REVENUE)
    sales_tax = get_account(company, CODES.SALES_TAX_PAYABLE)
    credits = get_account(company, CODES.CUSTOMER_CREDITS)

    subtotal = int(credit_note.subtotal_cents or 0)
    tax = int(credit_note.tax_cents or 0)
    total = int(credit_note.total_cents or 0)
    if total <= 0:
        return None

    entry = _create_entry(
        company=company,
        source_type="credit_note",
        source_id=credit_note.id,
        entry_date=timezone.localdate(),
        memo=f"Credit Note {credit_note.number or str(credit_note.id)[:8]}",
        created_by=getattr(getattr(credit_note, "created_by", None), "user", None),
    )

    # Immutable once lines exist
    if entry.lines.exists():
        # Ensure CreditNote is marked posted if journal exists (idempotency)
        if not credit_note.journal_entry_id or credit_note.status != CreditNoteStatus.POSTED:
            credit_note.journal_entry = entry
            credit_note.status = CreditNoteStatus.POSTED
            credit_note.posted_at = credit_note.posted_at or timezone.now()
            # Allocation might be missing from older rows; keep existing values
            credit_note.save(update_fields=["journal_entry", "status", "posted_at", "updated_at"])
        return entry

    # Decide whether credit reduces AR or becomes customer credit
    invoice_total = int(invoice.total_cents or 0)
    paid = int(getattr(invoice, "amount_paid_cents", 0) or 0)
    remaining_ar = max(invoice_total - paid, 0)

    ar_credit = min(total, remaining_ar)
    credit_liability = max(total - ar_credit, 0)

    lines = [
        # Reverse revenue/tax (debits)
        {
            "account": revenue,
            "description": "Reverse revenue (credit note)",
            "debit_cents": subtotal,
            "credit_cents": 0,
            "client": invoice.client,
            "project": getattr(invoice, "project", None),
        },
    ]
    if tax:
        lines.append(
            {
                "account": sales_tax,
                "description": "Reverse sales tax (credit note)",
                "debit_cents": tax,
                "credit_cents": 0,
                "client": invoice.client,
                "project": getattr(invoice, "project", None),
            }
        )

    # Credits: reduce AR and/or create customer credit liability
    if ar_credit:
        lines.append(
            {
                "account": ar,
                "description": "Reduce Accounts Receivable (credit note)",
                "debit_cents": 0,
                "credit_cents": ar_credit,
                "client": invoice.client,
                "project": getattr(invoice, "project", None),
            }
        )
    if credit_liability:
        lines.append(
            {
                "account": credits,
                "description": "Customer credit created (credit note)",
                "debit_cents": 0,
                "credit_cents": credit_liability,
                "client": invoice.client,
                "project": getattr(invoice, "project", None),
            }
        )

    _replace_lines(entry, lines)

    credit_note.journal_entry = entry
    credit_note.status = CreditNoteStatus.POSTED
    credit_note.posted_at = timezone.now()
    credit_note.ar_applied_cents = int(ar_credit)
    credit_note.customer_credit_cents = int(credit_liability)
    credit_note.save(update_fields=["journal_entry", "status", "posted_at", "ar_applied_cents", "customer_credit_cents", "updated_at"])

    # If any credit becomes customer credit (liability), record it in the client credit ledger.
    try:
        if int(credit_note.customer_credit_cents or 0) > 0 and invoice.client_id:
            from payments.models import ClientCreditLedgerEntry
            from django.db.models import Sum
            exists = ClientCreditLedgerEntry.objects.filter(
                company=company,
                client=invoice.client,
                invoice=invoice,
                cents_delta__gt=0,
                reason__icontains="Credit note",
            ).exists()
            if not exists:
                ClientCreditLedgerEntry.objects.create(
                    company=company,
                    client=invoice.client,
                    invoice=invoice,
                    cents_delta=int(credit_note.customer_credit_cents or 0),
                    reason=f"Credit note {credit_note.number or str(credit_note.id)[:8]} customer credit",
                    created_by=getattr(credit_note, "created_by", None),
                )
            # keep rollup synced
            invoice.client.credit_cents = (
                ClientCreditLedgerEntry.objects.filter(company=company, client=invoice.client, deleted_at__isnull=True)
                .aggregate(total=Sum("cents_delta"))
                .get("total") or 0
            )
            invoice.client.save(update_fields=["credit_cents", "updated_at"])
    except Exception:
        pass

    # Recompute stored invoice balance now that credits changed.
    try:
        from payments.services import recalc_invoice_financials

        recalc_invoice_financials(invoice)
    except Exception:
        pass



    # Audit
    try:
        log_event(
            company=company,
            actor=getattr(credit_note, "created_by", None),
            event_type="financial.credit_note.posted",
            object_type="CreditNote",
            object_id=credit_note.id,
            summary=f"Credit note posted: {credit_note.number or str(credit_note.id)[:8]}",
            payload={
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.number,
                "total_cents": total,
                "ar_credit_cents": ar_credit,
                "customer_credit_cents": credit_liability,
                "journal_entry_id": str(entry.id),
            },
        )
    except Exception:
        # Avoid breaking posting if audit fails
        pass

    return entry


@transaction.atomic
def post_client_credit_application_if_needed(app) -> JournalEntry | None:
    """Post a client credit application (consume liability, reduce AR)."""
    from payments.models import ClientCreditApplication
    if not isinstance(app, ClientCreditApplication):
        app = ClientCreditApplication.objects.get(pk=getattr(app, "pk", None))

    if app.deleted_at:
        return None
    if not app.cents or int(app.cents) <= 0:
        return None

    if app.journal_entry_id:
        return app.journal_entry

    company = app.company
    credits = get_account(company, CODES.CUSTOMER_CREDITS)
    ar = get_account(company, CODES.AR)

    entry = _create_entry(
        company=company,
        source_type="credit_application",
        source_id=app.id,
        entry_date=timezone.localdate(),
        memo=f"Apply client credit to invoice {getattr(getattr(app, 'invoice', None), 'number', '') or str(app.invoice_id)[:8]}",
        created_by=getattr(getattr(app, "created_by", None), "user", None),
    )

    if entry.lines.exists():
        app.journal_entry = entry
        app.save(update_fields=["journal_entry", "updated_at"])
        return entry

    amount = int(app.cents)

    lines = [
        {
            "account": credits,
            "description": "Reduce customer credits",
            "debit_cents": amount,
            "credit_cents": 0,
        },
        {
            "account": ar,
            "description": "Reduce accounts receivable",
            "debit_cents": 0,
            "credit_cents": amount,
        },
    ]
    _replace_lines(entry, lines)

    app.journal_entry = entry
    app.save(update_fields=["journal_entry", "updated_at"])

    return entry
