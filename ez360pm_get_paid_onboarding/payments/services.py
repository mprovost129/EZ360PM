from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from django.conf import settings

from audit.services import log_event
from crm.models import Client
from documents.models import Document, DocumentStatus, DocumentType

from .models import ClientCreditApplication, ClientCreditLedgerEntry, Payment, PaymentStatus

from .models import StripeConnectAccount, StripeConnectStatus



def _sum_posted_credit_applied_cents(invoice: Document) -> int:
    from django.db.models import Sum
    from documents.models import CreditNote, CreditNoteStatus

    agg = (
        CreditNote.objects.filter(invoice=invoice, status=CreditNoteStatus.POSTED, deleted_at__isnull=True)
        .aggregate(total=Sum("ar_applied_cents"))
    )
    return int(agg.get("total") or 0)




def _sum_credit_applications_cents(invoice: Document) -> int:
    agg = (
        ClientCreditApplication.objects.filter(invoice=invoice, deleted_at__isnull=True)
        .aggregate(total=Sum("cents"))
    )
    return int(agg.get("total") or 0)


def _sum_successful_payments_cents(invoice: Document) -> int:
    # Net payments = amount - refunded.
    agg = (
        Payment.objects.filter(invoice=invoice, status__in=[PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED])
        .aggregate(total=Sum(models.F("amount_cents") - models.F("refunded_cents")))
    )
    return int(agg.get("total") or 0)


def _recalc_client_outstanding_cents(client: Client) -> int:
    agg = (
        Document.objects.filter(
            company=client.company,
            client=client,
            doc_type=DocumentType.INVOICE,
        )
        .exclude(status=DocumentStatus.VOID)
        .aggregate(total=Sum("balance_due_cents"))
    )
    return int(agg.get("total") or 0)



def client_credit_balance_cents(client: Client) -> int:
    agg = (
        ClientCreditLedgerEntry.objects.filter(company=client.company, client=client, deleted_at__isnull=True)
        .aggregate(total=Sum("cents_delta"))
    )
    return int(agg.get("total") or 0)


def sync_client_credit_rollup(client: Client) -> None:
    client.credit_cents = client_credit_balance_cents(client)
    client.save(update_fields=["credit_cents", "updated_at"])

@transaction.atomic
def recalc_invoice_financials(invoice: Document, *, actor=None) -> None:
    """Recompute stored invoice amounts from successful payments + posted credit notes + credit applications."""
    if not invoice or invoice.deleted_at:
        return
    if invoice.doc_type != DocumentType.INVOICE:
        return

    paid_cents = _sum_successful_payments_cents(invoice)
    credit_note_applied = _sum_posted_credit_applied_cents(invoice)
    credit_apps = _sum_credit_applications_cents(invoice)

    invoice.amount_paid_cents = max(0, int(paid_cents))
    invoice.balance_due_cents = max(
        0,
        int(invoice.total_cents or 0) - int(invoice.amount_paid_cents or 0) - int(credit_note_applied) - int(credit_apps),
    )

    if invoice.status != DocumentStatus.VOID:
        total = int(invoice.total_cents or 0)
        paid_like = total - int(invoice.balance_due_cents or 0)
        if total > 0 and paid_like >= total:
            invoice.status = DocumentStatus.PAID
        elif paid_like > 0 and paid_like < total:
            invoice.status = DocumentStatus.PARTIALLY_PAID

    invoice.save(update_fields=["amount_paid_cents", "balance_due_cents", "status", "updated_at"])

    # Update client rollups
    if invoice.client_id:
        client = invoice.client
        assert client is not None
        client.outstanding_cents = _recalc_client_outstanding_cents(client)
        client.save(update_fields=["outstanding_cents", "updated_at"])

    if actor is not None:
        log_event(
            company=invoice.company,
            actor=actor,
            event_type="financial.invoice.recalc",
            object_type="Document",
            object_id=str(invoice.id),
            summary=f"Recalculated invoice {invoice.number or invoice.id}",
        )


@transaction.atomic
def apply_payment_and_recalc(payment: Payment, *, actor=None) -> None:
    """Apply a payment to its invoice (if any) and recompute invoice + client rollups.

    Rules (v1):
    - Only SUCCEEDED payments affect balances.
    - Overpayment creates client credit (and reduces invoice balance to 0).
    """
    invoice = payment.invoice
    if not invoice:
        return

    if invoice.doc_type != DocumentType.INVOICE:
        return

    prev_balance = int(invoice.balance_due_cents or 0)

    # Ensure payment.client matches invoice.client when possible.
    if invoice.client and payment.client_id != invoice.client_id:
        payment.client = invoice.client
        payment.save(update_fields=["client", "updated_at"])

    # Recalc invoice financials from successful payments + credits.
    recalc_invoice_financials(invoice, actor=actor)


    # Handle overpayment: if successful payments exceed total.
    overpay = max(0, invoice.amount_paid_cents - int(invoice.total_cents or 0))
    if overpay and invoice.client_id:
        client = invoice.client
        assert client is not None

        credited = (
            ClientCreditLedgerEntry.objects.filter(company=client.company, client=client, invoice=invoice, cents_delta__gt=0)
            .aggregate(total=Sum("cents_delta"))
            .get("total")
            or 0
        )
        delta = max(0, int(overpay) - int(credited))
        if delta:
            ClientCreditLedgerEntry.objects.create(
                company=client.company,
                client=client,
                invoice=invoice,
                cents_delta=delta,
                reason=f"Overpayment credit from invoice {invoice.number or invoice.id}",
                created_by=actor,
            )
        # Keep rollup in sync from ledger
        sync_client_credit_rollup(client)


    # Update client outstanding
    if invoice.client_id:
        client = invoice.client
        assert client is not None
        client.outstanding_cents = _recalc_client_outstanding_cents(client)
        client.save(update_fields=["outstanding_cents", "updated_at"])

    # Audit
    if actor is not None:
        log_event(
            company=invoice.company,
            actor=actor,
            event_type="payment.applied",
            object_type="Document",
            object_id=str(invoice.id),
            summary=f"Payment applied to invoice {invoice.number or invoice.id}",
            payload={
                "payment_id": str(payment.id),
                "invoice_id": str(invoice.id),
                "paid_cents": invoice.amount_paid_cents,
                "balance_due_cents": invoice.balance_due_cents,
                "prev_balance": prev_balance,
            },
        )


@transaction.atomic
def apply_client_credit_to_invoice(
    invoice: Document,
    *,
    cents: int,
    actor=None,
    memo: str = "",
) -> ClientCreditApplication:
    """Consume existing client credit and apply it to an invoice balance.

    Creates:
    - ClientCreditApplication record
    - ClientCreditLedgerEntry (negative delta)
    - JournalEntry (DR Customer Credits, CR Accounts Receivable)
    """
    if not invoice or invoice.deleted_at:
        raise ValueError("Invoice not found.")
    if invoice.doc_type != DocumentType.INVOICE:
        raise ValueError("Credit can only be applied to invoices.")
    if invoice.status == DocumentStatus.VOID:
        raise ValueError("Cannot apply credit to a void invoice.")
    if not invoice.client_id:
        raise ValueError("Invoice has no client.")

    client = invoice.client
    assert client is not None

    cents = int(cents or 0)
    if cents <= 0:
        raise ValueError("Amount must be greater than 0.")

    # available credit
    available = client_credit_balance_cents(client)
    if available <= 0:
        raise ValueError("No available client credit.")

    # remaining invoice balance (effective)
    remaining = max(0, int(invoice.balance_due_cents or 0))
    # Ensure stored balance is up to date
    recalc_invoice_financials(invoice, actor=actor)
    remaining = max(0, int(invoice.balance_due_cents or 0))

    apply_cents = min(cents, available, remaining)
    if apply_cents <= 0:
        raise ValueError("Nothing to apply.")

    app = ClientCreditApplication.objects.create(
        company=invoice.company,
        client=client,
        invoice=invoice,
        cents=apply_cents,
        memo=(memo or "")[:240],
        created_by=actor,
        applied_at=timezone.now(),
    )

    ClientCreditLedgerEntry.objects.create(
        company=invoice.company,
        client=client,
        invoice=invoice,
        cents_delta=-apply_cents,
        reason=f"Applied credit to invoice {invoice.number or invoice.id}",
        created_by=actor,
    )

    # Accounting
    try:
        from accounting.services import post_client_credit_application_if_needed

        entry = post_client_credit_application_if_needed(app)
        if entry and not app.journal_entry_id:
            app.journal_entry = entry
            app.save(update_fields=["journal_entry", "updated_at"])
    except Exception:
        # Accounting posting is best-effort; do not break credit application.
        pass

    # Recalc invoice + client rollups
    recalc_invoice_financials(invoice, actor=actor)
    sync_client_credit_rollup(client)

    if actor is not None:
        log_event(
            company=invoice.company,
            actor=actor,
            event_type="financial.credit.applied",
            object_type="Document",
            object_id=str(invoice.id),
            summary=f"Applied ${apply_cents/100:.2f} credit to invoice {invoice.number or invoice.id}",
        )

    return app


@transaction.atomic
def refund_payment_and_recalc(refund, *, actor=None) -> None:
    """Apply a succeeded refund to its payment/invoice and recompute rollups.

    Rules:
    - Only SUCCEEDED refunds affect balances.
    - Refund amount reduces payment.refunded_cents.
    - Payment becomes REFUNDED when fully refunded.
    """
    from .models import PaymentRefundStatus

    if refund.status != PaymentRefundStatus.SUCCEEDED:
        return

    payment = refund.payment
    if payment.deleted_at:
        return

    # Prevent double-applying the same refund by ensuring refunded_cents includes it.
    # We treat refund records as the source of truth and sync the payment rollup.
    refunded_total = (
        payment.refunds.filter(deleted_at__isnull=True, status=PaymentRefundStatus.SUCCEEDED)
        .aggregate(total=Sum("cents"))
        .get("total")
        or 0
    )
    payment.refunded_cents = int(refunded_total or 0)

    if payment.refunded_cents >= int(payment.amount_cents or 0) and int(payment.amount_cents or 0) > 0:
        payment.status = PaymentStatus.REFUNDED
    else:
        # Keep succeeded if partially refunded.
        if payment.status == PaymentStatus.REFUNDED:
            payment.status = PaymentStatus.SUCCEEDED

    payment.save(update_fields=["refunded_cents", "status", "updated_at"])

    # Recalc invoice + client rollups
    invoice = payment.invoice
    if invoice and not invoice.deleted_at:
        recalc_invoice_financials(invoice, actor=actor)


# --------------------------------------------------------------------------------------
# Stripe Connect (company payouts for invoice payments)
# --------------------------------------------------------------------------------------


def stripe_connect_enabled() -> bool:
    if not getattr(settings, "STRIPE_SECRET_KEY", ""):
        return False
    raw = str(getattr(settings, "STRIPE_CONNECT_ENABLED", "1") or "1").strip().lower()
    return raw in {"1", "true", "yes", "y", "on"}


def get_or_create_stripe_connect_account(company) -> StripeConnectAccount:
    obj = StripeConnectAccount.objects.filter(company=company).first()
    if obj:
        return obj
    return StripeConnectAccount.objects.create(company=company, status=StripeConnectStatus.NOT_CONNECTED)


def get_connected_account_id(company) -> str:
    sca = StripeConnectAccount.objects.filter(company=company).first()
    if not sca:
        return ""
    return (sca.stripe_account_id or "").strip()


def sync_stripe_connect_account(company, *, account_id: str | None = None) -> StripeConnectAccount:
    """Fetch the Stripe account and sync status flags to DB."""
    sca = get_or_create_stripe_connect_account(company)
    if not stripe_connect_enabled():
        return sca

    acct_id = (account_id or sca.stripe_account_id or "").strip()
    if not acct_id:
        return sca

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY
    acct = stripe.Account.retrieve(acct_id)

    charges_enabled = bool(acct.get("charges_enabled"))
    payouts_enabled = bool(acct.get("payouts_enabled"))
    details_submitted = bool(acct.get("details_submitted"))
    disabled_reason = str(((acct.get("requirements") or {}).get("disabled_reason") or ""))

    status = StripeConnectStatus.PENDING
    if charges_enabled and payouts_enabled:
        status = StripeConnectStatus.ACTIVE
    elif disabled_reason:
        status = StripeConnectStatus.RESTRICTED

    sca.stripe_account_id = acct_id
    sca.charges_enabled = charges_enabled
    sca.payouts_enabled = payouts_enabled
    sca.details_submitted = details_submitted
    sca.disabled_reason = disabled_reason
    sca.requirements_json = dict(acct.get("requirements") or {})
    sca.status = status
    sca.last_sync_at = timezone.now()

    sca.save(
        update_fields=[
            "stripe_account_id",
            "charges_enabled",
            "payouts_enabled",
            "details_submitted",
            "disabled_reason",
            "requirements_json",
            "status",
            "last_sync_at",
            "updated_at",
            "revision",
        ]
    )
    return sca


def ensure_stripe_connect_account_and_link(company, *, refresh_url: str, return_url: str) -> tuple[StripeConnectAccount, str]:
    """Create/reuse an Express account and return an onboarding URL."""
    sca = get_or_create_stripe_connect_account(company)
    if not stripe_connect_enabled():
        raise RuntimeError("Stripe Connect is not configured.")

    import stripe

    stripe.api_key = settings.STRIPE_SECRET_KEY

    if not (sca.stripe_account_id or "").strip():
        acct = stripe.Account.create(
            type="express",
            business_type="company",
            metadata={"company_id": str(company.id)},
        )
        sca.stripe_account_id = str(acct.get("id") or "")
        sca.status = StripeConnectStatus.PENDING
        sca.save(update_fields=["stripe_account_id", "status", "updated_at", "revision"])

    link = stripe.AccountLink.create(
        account=sca.stripe_account_id,
        refresh_url=refresh_url,
        return_url=return_url,
        type="account_onboarding",
    )

    # best-effort sync
    try:
        sync_stripe_connect_account(company)
    except Exception:
        pass

    return sca, str(link.get("url") or "")
