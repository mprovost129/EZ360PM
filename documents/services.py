from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import Document, DocumentType, NumberingScheme, Decimal


_TOKEN_RE = re.compile(r"\{(YY|YYYY|MM|DD|SEQ(?::\d+)?)\}")


@dataclass
class NumberingContext:
    today: date
    seq: int


def _format_pattern(pattern: str, ctx: NumberingContext) -> str:
    def repl(m: re.Match) -> str:
        token = m.group(1)
        if token == "YY":
            return f"{ctx.today.year % 100:02d}"
        if token == "YYYY":
            return f"{ctx.today.year:04d}"
        if token == "MM":
            return f"{ctx.today.month:02d}"
        if token == "DD":
            return f"{ctx.today.day:02d}"
        if token.startswith("SEQ"):
            width = 0
            if ":" in token:
                try:
                    width = int(token.split(":", 1)[1])
                except Exception:
                    width = 0
            return f"{ctx.seq:0{width}d}" if width else str(ctx.seq)
        return m.group(0)

    return _TOKEN_RE.sub(repl, pattern or "{YY}/{MM}/{SEQ:3}")


@transaction.atomic
def ensure_numbering_scheme(company) -> NumberingScheme:
    scheme, _ = NumberingScheme.objects.select_for_update().get_or_create(company=company)
    return scheme


@transaction.atomic
def allocate_document_number(company, doc_type: str) -> str:
    scheme = ensure_numbering_scheme(company)
    today = timezone.localdate()
    if doc_type == DocumentType.INVOICE:
        seq = int(scheme.invoice_seq or 1)
        number = _format_pattern(scheme.invoice_pattern, NumberingContext(today=today, seq=seq))
        scheme.invoice_seq = seq + 1
        scheme.save(update_fields=["invoice_seq", "updated_at"])
        return number
    if doc_type == DocumentType.ESTIMATE:
        seq = int(scheme.estimate_seq or 1)
        number = _format_pattern(scheme.estimate_pattern, NumberingContext(today=today, seq=seq))
        scheme.estimate_seq = seq + 1
        scheme.save(update_fields=["estimate_seq", "updated_at"])
        return number
    if doc_type == DocumentType.PROPOSAL:
        seq = int(scheme.proposal_seq or 1)
        number = _format_pattern(scheme.proposal_pattern, NumberingContext(today=today, seq=seq))
        scheme.proposal_seq = seq + 1
        scheme.save(update_fields=["proposal_seq", "updated_at"])
        return number
    # fallback
    seq = int(scheme.invoice_seq or 1)
    number = _format_pattern("{YY}/{MM}/{SEQ:3}", NumberingContext(today=today, seq=seq))
    scheme.invoice_seq = seq + 1
    scheme.save(update_fields=["invoice_seq", "updated_at"])
    return number


def recalc_document_totals(doc: Document) -> None:
    from decimal import Decimal
    from .models import DocumentLineItem

    subtotal = Decimal("0")
    tax = Decimal("0")
    total = Decimal("0")

    items = list(DocumentLineItem.objects.filter(document=doc, deleted_at__isnull=True).order_by("sort_order", "created_at"))

    # ------------------------------------------------------------------
    # Tax rollup policy (Phase 9)
    # ------------------------------------------------------------------
    # The paper-style composer uses `Document.sales_tax_percent` and auto-computes tax per taxable line
    # in the browser. Server must remain the source of truth, so we recompute here as well so:
    #  - totals remain correct if JS is disabled
    #  - changing the tax percent reliably updates all taxable lines
    #
    # If sales_tax_percent is 0, we respect the per-line tax inputs (manual tax scenarios).
    sales_tax_pct = Decimal("0")
    try:
        sales_tax_pct = Decimal(getattr(doc, "sales_tax_percent", 0) or 0)
    except Exception:
        sales_tax_pct = Decimal("0")

    if sales_tax_pct > 0:
        changed = []
        now = timezone.now()
        for li in items:
            line_sub = int(li.line_subtotal_cents or 0)
            if bool(li.is_taxable):
                line_tax = int((Decimal(line_sub) * (sales_tax_pct / Decimal("100"))).quantize(Decimal("1")))
            else:
                line_tax = 0
            line_total = line_sub + line_tax

            if int(li.tax_cents or 0) != line_tax or int(li.line_total_cents or 0) != line_total:
                li.tax_cents = line_tax
                li.line_total_cents = line_total
                li.updated_at = now
                changed.append(li)

        if changed:
            DocumentLineItem.objects.bulk_update(changed, ["tax_cents", "line_total_cents", "updated_at"])

        # Roll up totals
        for li in items:
            subtotal += int(li.line_subtotal_cents or 0)
            tax += int(li.tax_cents or 0)
            total += int(li.line_total_cents or 0)

        doc.subtotal_cents = int(subtotal)
        doc.tax_cents = int(tax)
        doc.total_cents = int(total)

        # Deposit requested (composer)
        deposit_cents = 0
        try:
            dtype = getattr(doc, "deposit_type", "none") or "none"
            dval = Decimal(getattr(doc, "deposit_value", 0) or 0)
            if dtype == getattr(Document.DepositType, "PERCENT", "percent"):
                if dval > 0:
                    deposit_cents = int((Decimal(total) * (dval / Decimal("100"))).quantize(Decimal("1")))
            elif dtype == getattr(Document.DepositType, "FIXED", "fixed"):
                if dval > 0:
                    deposit_cents = int((dval.quantize(Decimal("0.01")) * Decimal("100")).quantize(Decimal("1")))
            else:
                deposit_cents = 0
        except Exception:
            deposit_cents = 0

        doc.deposit_cents = int(deposit_cents or 0)

        # invoice balance fields
        if doc.doc_type == DocumentType.INVOICE:
            paid = int(doc.amount_paid_cents or 0)
            doc.balance_due_cents = int(max(0, total - paid))
        doc.save(update_fields=["subtotal_cents", "tax_cents", "total_cents", "deposit_cents", "balance_due_cents", "updated_at"])
