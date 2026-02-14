from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

from django.db.models import F, Sum

from companies.models import Company


@dataclass(frozen=True)
class ReconciliationFlag:
    key: str
    ok: bool
    message: str


def _safe_int(v) -> int:
    try:
        return int(v or 0)
    except Exception:
        return 0


def _sum(qs, expr) -> int:
    try:
        return _safe_int(qs.aggregate(s=Sum(expr)).get("s"))
    except Exception:
        return 0


def reconcile_company(company: Company) -> Dict[str, object]:
    """Compute a practical reconciliation snapshot for a company.

    This is *not* a full accounting audit; it's a launch-readiness sanity check that
    catches the most common "money loop" failures:
    - invoices not posted to AR
    - credits not posted to liability
    - payments drift vs invoice paid totals
    """
    from documents.models import Document, DocumentStatus, DocumentType
    from payments.models import Payment, PaymentStatus, ClientCreditLedgerEntry, ClientCreditApplication
    from accounting.models import Account, JournalLine

    invoices = (
        Document.objects.filter(company=company, doc_type=DocumentType.INVOICE, deleted_at__isnull=True)
        .exclude(status=DocumentStatus.VOID)
    )
    posted_invoices = invoices.exclude(status=DocumentStatus.DRAFT)

    payments = Payment.objects.filter(company=company, deleted_at__isnull=True)
    payments_net_cents = _sum(
        payments.filter(status__in=[PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED]),
        F("amount_cents") - F("refunded_cents"),
    )

    credit_ledger = ClientCreditLedgerEntry.objects.filter(company=company, deleted_at__isnull=True)
    credit_ledger_balance = _sum(credit_ledger, "cents_delta")

    credit_apps = ClientCreditApplication.objects.filter(company=company, deleted_at__isnull=True)
    credit_applied = _sum(credit_apps, "cents")

    invoices_total = _sum(posted_invoices, "total_cents")
    invoices_balance_due = _sum(posted_invoices, "balance_due_cents")
    invoices_paid = _sum(posted_invoices, "amount_paid_cents")

    def acct_balance(code: str) -> int:
        acc = Account.objects.filter(company=company, code=code).first()
        if not acc:
            return 0
        debit = _sum(JournalLine.objects.filter(account=acc, deleted_at__isnull=True), "debit_cents")
        credit = _sum(JournalLine.objects.filter(account=acc, deleted_at__isnull=True), "credit_cents")
        return int(debit) - int(credit)

    ar_balance = acct_balance("1100")
    cash_balance = acct_balance("1000")
    # For liabilities, a *credit* balance is normal; convert to positive numbers for display.
    customer_credits_balance = -acct_balance("2200")

    flags: List[ReconciliationFlag] = []

    flags.append(
        ReconciliationFlag(
            key="ar_matches_invoice_balances",
            ok=(ar_balance == invoices_balance_due),
            message=f"AR ledger {ar_balance} vs invoices balance_due {invoices_balance_due}",
        )
    )

    flags.append(
        ReconciliationFlag(
            key="customer_credits_matches_ledger",
            ok=(customer_credits_balance == credit_ledger_balance),
            message=f"Customer Credits acct {customer_credits_balance} vs credit ledger {credit_ledger_balance}",
        )
    )

    flags.append(
        ReconciliationFlag(
            key="payments_vs_invoice_paid",
            ok=(payments_net_cents >= invoices_paid),
            message=f"Payments net {payments_net_cents} vs invoices amount_paid {invoices_paid}",
        )
    )

    return {
        "company": company,
        "counts": {
            "invoices_posted": posted_invoices.count(),
            "payments_total": payments.count(),
            "credit_ledger_entries": credit_ledger.count(),
            "credit_applications": credit_apps.count(),
        },
        "money": {
            "invoices_total_cents": invoices_total,
            "invoices_paid_cents": invoices_paid,
            "invoices_balance_due_cents": invoices_balance_due,
            "payments_net_cents": payments_net_cents,
            "credit_ledger_balance_cents": credit_ledger_balance,
            "credit_applied_cents": credit_applied,
            "ar_balance_cents": ar_balance,
            "cash_balance_cents": cash_balance,
            "customer_credits_balance_cents": customer_credits_balance,
        },
        "flags": flags,
    }
