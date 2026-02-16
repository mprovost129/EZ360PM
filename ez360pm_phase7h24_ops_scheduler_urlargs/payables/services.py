from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from accounting.models import JournalEntry, JournalLine, DefaultAccountCodes, get_account
from companies.models import Company, EmployeeProfile

from .models import Bill, BillPayment


CODES = DefaultAccountCodes()


def _create_entry(*, company: Company, source_type: str, source_id, entry_date, memo: str, created_by=None) -> JournalEntry:
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
            description=(l.get("description") or "")[:240],
            debit_cents=int(l.get("debit_cents") or 0),
            credit_cents=int(l.get("credit_cents") or 0),
            client=l.get("client"),
            project=l.get("project"),
        )


@transaction.atomic
def post_bill_if_needed(bill: Bill) -> JournalEntry | None:
    if bill.deleted_at:
        return None
    if not bill.is_posted:
        return None

    company = bill.company
    ap = get_account(company, CODES.AP)

    bill.recalc_totals()
    total = int(bill.total_cents or 0)
    if total <= 0:
        return None

    entry = _create_entry(
        company=company,
        source_type="bill",
        source_id=bill.id,
        entry_date=bill.issue_date or timezone.localdate(),
        memo=f"Bill {bill.bill_number or str(bill.id)[:8]}",
        created_by=getattr(getattr(bill, "created_by", None), "user", None),
    )

    if entry.lines.exists():
        return entry

    # Debit each expense account by its line total
    lines: list[dict] = []
    for li in bill.lines.select_related("expense_account").all():
        amt = int(li.line_total_cents or 0)
        if amt <= 0:
            continue
        lines.append(
            {
                "account": li.expense_account,
                "description": li.description,
                "debit_cents": amt,
                "credit_cents": 0,
            }
        )

    # Tax (optional): treat as Expenses by default (can be improved later)
    tax = int(bill.tax_cents or 0)
    if tax:
        exp = get_account(company, CODES.EXPENSES)
        lines.append(
            {
                "account": exp,
                "description": "Tax",
                "debit_cents": tax,
                "credit_cents": 0,
            }
        )

    # Credit AP
    lines.append(
        {
            "account": ap,
            "description": "Accounts Payable",
            "debit_cents": 0,
            "credit_cents": total,
        }
    )

    _replace_lines(entry, lines)
    return entry


@transaction.atomic
def post_bill_payment_if_needed(payment: BillPayment) -> JournalEntry | None:
    bill = payment.bill
    if bill.deleted_at or payment.deleted_at:
        return None
    if not bill.is_posted:
        return None

    company = bill.company
    ap = get_account(company, CODES.AP)

    amount = int(payment.amount_cents or 0)
    if amount <= 0:
        return None

    # Prevent overpay (based on current balance)
    bill.recalc_totals()
    if amount > int(bill.balance_cents or 0):
        raise ValueError("Payment exceeds bill balance.")

    cash = payment.payment_account

    entry = _create_entry(
        company=company,
        source_type="bill_payment",
        source_id=payment.id,
        entry_date=payment.payment_date or timezone.localdate(),
        memo=f"Bill payment {bill.bill_number or str(bill.id)[:8]}",
        created_by=getattr(getattr(payment, "created_by", None), "user", None),
    )

    lines = [
        {
            "account": ap,
            "description": "Accounts Payable",
            "debit_cents": amount,
            "credit_cents": 0,
        },
        {
            "account": cash,
            "description": "Cash/Bank",
            "debit_cents": 0,
            "credit_cents": amount,
        },
    ]

    _replace_lines(entry, lines)

    # update bill amounts/status
    bill.recalc_totals()
    bill.save(update_fields=["subtotal_cents", "total_cents", "amount_paid_cents", "balance_cents", "status", "updated_at", "revision"])

    return entry
