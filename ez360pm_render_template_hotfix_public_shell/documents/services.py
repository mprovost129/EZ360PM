from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date

from django.db import transaction
from django.utils import timezone

from .models import Document, DocumentType, NumberingScheme


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
    subtotal = 0
    tax = 0
    total = 0
    for li in doc.line_items.filter(deleted_at__isnull=True).order_by("sort_order", "created_at"):
        subtotal += int(li.line_subtotal_cents or 0)
        tax += int(li.tax_cents or 0)
        total += int(li.line_total_cents or 0)

    doc.subtotal_cents = subtotal
    doc.tax_cents = tax
    doc.total_cents = total

    # invoice balance fields
    if doc.doc_type == DocumentType.INVOICE:
        paid = int(doc.amount_paid_cents or 0)
        doc.balance_due_cents = max(0, total - paid)
    doc.save(update_fields=["subtotal_cents", "tax_cents", "total_cents", "balance_due_cents", "updated_at"])
