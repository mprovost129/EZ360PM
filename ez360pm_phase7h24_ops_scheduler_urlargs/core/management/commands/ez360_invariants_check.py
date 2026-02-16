from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db.models import Sum, F

from accounting.models import JournalEntry
from crm.models import Client
from documents.models import CreditNote, CreditNoteStatus, Document, DocumentType
from payments.models import (
    ClientCreditApplication,
    ClientCreditLedgerEntry,
    Payment,
    PaymentRefund,
    PaymentRefundStatus,
    PaymentStatus,
)


class Command(BaseCommand):
    help = "Validate key financial invariants (documents/payments/credits/journals) for EZ360PM."

    def add_arguments(self, parser):
        parser.add_argument("--company-id", default=None, help="Optional Company ID to scope checks.")
        parser.add_argument("--limit", type=int, default=300, help="Max rows to scan per section (default 300).")
        parser.add_argument("--fail-fast", action="store_true", help="Exit on first failure.")
        parser.add_argument("--quiet", action="store_true", help="Only print failures/warnings.")

    def handle(self, *args, **options):
        company_id = options.get("company_id")
        limit = int(options.get("limit") or 0) or 300
        fail_fast = bool(options.get("fail_fast"))
        quiet = bool(options.get("quiet"))

        def _fail(msg: str) -> None:
            nonlocal failures
            failures += 1
            self.stdout.write(self.style.ERROR(msg))
            if fail_fast:
                raise SystemExit(2)

        def _warn(msg: str) -> None:
            nonlocal warnings
            warnings += 1
            self.stdout.write(self.style.WARNING(msg))

        failures = 0
        warnings = 0

        if not quiet:
            self.stdout.write("EZ360PM invariants check")
            self.stdout.write("-" * 30)

        # ------------------------------------------------------------------
        # Invoices (Document)
        # ------------------------------------------------------------------
        inv_qs = Document.objects.filter(doc_type=DocumentType.INVOICE, deleted_at__isnull=True).order_by("-updated_at")
        if company_id:
            inv_qs = inv_qs.filter(company_id=company_id)
        invoices = list(inv_qs[:limit])
        if not quiet:
            self.stdout.write(f"Invoices scanned: {len(invoices)}")

        for inv in invoices:
            subtotal = int(inv.subtotal_cents or 0)
            tax = int(inv.tax_cents or 0)
            total = int(inv.total_cents or 0)
            paid_snapshot = int(inv.amount_paid_cents or 0)
            bal_snapshot = int(inv.balance_due_cents or 0)

            if total != subtotal + tax:
                _fail(
                    f"[INV {inv.id}] total mismatch: total={total} subtotal={subtotal} tax={tax} (expected {subtotal + tax})"
                )

            if paid_snapshot < 0 or paid_snapshot > max(0, total):
                _fail(f"[INV {inv.id}] amount_paid_cents out of range: paid={paid_snapshot} total={total}")

            if bal_snapshot < 0:
                _fail(f"[INV {inv.id}] balance_due_cents negative: {bal_snapshot}")

            # Net successful payments = amount - refunded (succeeded/refunded statuses)
            net_payments = (
                Payment.objects.filter(
                    invoice=inv,
                    deleted_at__isnull=True,
                    status__in=[PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED],
                )
                .aggregate(total=Sum(F("amount_cents") - F("refunded_cents")))
                .get("total")
                or 0
            )
            net_payments = int(net_payments)

            if net_payments < 0:
                _fail(f"[INV {inv.id}] net payments negative: {net_payments}")

            if net_payments > paid_snapshot:
                _fail(
                    f"[INV {inv.id}] net payments exceed invoice.amount_paid_cents: net={net_payments} paid={paid_snapshot}"
                )

            # Credit applications (client credit) + posted credit notes applied to A/R
            credit_apps = (
                ClientCreditApplication.objects.filter(invoice=inv, deleted_at__isnull=True).aggregate(total=Sum("cents")).get("total")
                or 0
            )
            credit_apps = int(credit_apps)

            posted_cn_applied = (
                CreditNote.objects.filter(invoice=inv, deleted_at__isnull=True, status=CreditNoteStatus.POSTED)
                .aggregate(total=Sum("ar_applied_cents"))
                .get("total")
                or 0
            )
            posted_cn_applied = int(posted_cn_applied)

            if credit_apps < 0:
                _fail(f"[INV {inv.id}] credit applications negative: {credit_apps}")
            if posted_cn_applied < 0:
                _fail(f"[INV {inv.id}] posted credit note applied negative: {posted_cn_applied}")

            # Effective balance sanity: should never be negative, and should not exceed total.
            try:
                eff = int(inv.balance_due_effective_cents())
            except Exception as e:
                _fail(f"[INV {inv.id}] balance_due_effective_cents() crashed: {e}")
                continue

            if eff < 0:
                _fail(f"[INV {inv.id}] effective balance negative: {eff}")

            if eff > max(0, total):
                _warn(f"[INV {inv.id}] effective balance exceeds total: eff={eff} total={total}")

            # Basic expected (ignoring credits): max(0, total - paid_snapshot)
            basic_expected = max(0, total - paid_snapshot)
            if bal_snapshot != basic_expected:
                # Not always fatal because credits affect effective balance.
                _warn(
                    f"[INV {inv.id}] balance_due snapshot differs from basic expected: bal={bal_snapshot} expected={basic_expected} effective={eff}"
                )

            # Credits should never "apply" beyond total.
            if credit_apps + posted_cn_applied > max(0, total):
                _warn(
                    f"[INV {inv.id}] credits exceed invoice total: credit_apps={credit_apps} credit_notes_applied={posted_cn_applied} total={total}"
                )

        # ------------------------------------------------------------------
        # Payments & refunds
        # ------------------------------------------------------------------
        pay_qs = Payment.objects.filter(deleted_at__isnull=True).order_by("-updated_at")
        if company_id:
            pay_qs = pay_qs.filter(company_id=company_id)
        payments = list(pay_qs[:limit])
        if not quiet:
            self.stdout.write(f"Payments scanned: {len(payments)}")

        for pmt in payments:
            amt = int(pmt.amount_cents or 0)
            refunded = int(pmt.refunded_cents or 0)

            if amt < 0:
                _fail(f"[PAY {pmt.id}] amount_cents negative: {amt}")

            if refunded < 0 or refunded > max(0, amt):
                _fail(f"[PAY {pmt.id}] refunded_cents out of range: refunded={refunded} amount={amt}")

            refund_sum = (
                PaymentRefund.objects.filter(payment=pmt, deleted_at__isnull=True, status=PaymentRefundStatus.SUCCEEDED)
                .aggregate(total=Sum("cents"))
                .get("total")
                or 0
            )
            refund_sum = int(refund_sum)

            if refund_sum < 0 or refund_sum > max(0, amt):
                _fail(f"[PAY {pmt.id}] succeeded refunds out of range: refunds={refund_sum} amount={amt}")

            if refund_sum != refunded:
                # Not fatal; some flows may not backfill refunded_cents consistently.
                _warn(f"[PAY {pmt.id}] refunded_cents mismatch: field={refunded} succeeded_refunds={refund_sum}")

            net = amt - refunded
            if net < 0:
                _fail(f"[PAY {pmt.id}] net amount negative: amount={amt} refunded={refunded}")

        # ------------------------------------------------------------------
        # Client credit ledger & applications
        # ------------------------------------------------------------------
        client_qs = Client.objects.filter(deleted_at__isnull=True).order_by("-updated_at")
        if company_id:
            client_qs = client_qs.filter(company_id=company_id)
        clients = list(client_qs[:limit])
        if not quiet:
            self.stdout.write(f"Clients scanned: {len(clients)}")

        for c in clients:
            ledger_sum = (
                ClientCreditLedgerEntry.objects.filter(company=c.company, client=c, deleted_at__isnull=True)
                .aggregate(total=Sum("cents_delta"))
                .get("total")
                or 0
            )
            ledger_sum = int(ledger_sum)
            if ledger_sum != int(c.credit_cents or 0):
                _warn(
                    f"[CLIENT {c.id}] credit_cents mismatch: client.credit_cents={int(c.credit_cents or 0)} ledger_sum={ledger_sum}"
                )

            if int(c.credit_cents or 0) < 0:
                _warn(f"[CLIENT {c.id}] credit_cents is negative: {int(c.credit_cents or 0)}")

            # Credit applications should not exceed (ledger_sum + small tolerance) across all invoices,
            # but we only sanity-check per invoice.
            app_qs = ClientCreditApplication.objects.filter(client=c, deleted_at__isnull=True).select_related("invoice")[:50]
            for app in app_qs:
                if app.cents <= 0:
                    _fail(f"[CREDIT_APP {app.id}] cents must be positive: {app.cents}")
                if app.invoice.company_id != c.company_id:
                    _fail(f"[CREDIT_APP {app.id}] invoice company mismatch")
                if app.invoice.client_id != c.id:
                    _fail(f"[CREDIT_APP {app.id}] invoice client mismatch (invoice.client_id={app.invoice.client_id})")

        # ------------------------------------------------------------------
        # Journals
        # ------------------------------------------------------------------
        je_qs = JournalEntry.objects.all().order_by("-created_at")
        if company_id:
            je_qs = je_qs.filter(company_id=company_id)
        jes = list(je_qs[:limit])
        if not quiet:
            self.stdout.write(f"Journal entries scanned: {len(jes)}")

        for je in jes:
            if je.source_type and not je.source_id:
                _fail(f"[JE {je.id}] source_type set but source_id missing: source_type={je.source_type}")

            deb = int(je.total_debits_cents or 0)
            cred = int(je.total_credits_cents or 0)
            if deb != cred:
                _fail(f"[JE {je.id}] not balanced: debits={deb} credits={cred} memo='{je.memo}'")

        if not quiet:
            self.stdout.write("-" * 30)
            self.stdout.write(f"Warnings: {warnings}")
            self.stdout.write(f"Failures: {failures}")

        if failures:
            raise SystemExit(2)
