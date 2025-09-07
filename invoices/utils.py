# invoices/utils.py
from __future__ import annotations

import re
from datetime import date
from django.db import transaction, IntegrityError
from django.utils import timezone

from company.models import Company
from .models import Invoice

# Matches PREFIX-YYYYMM-SEQ (e.g., "INV-202509-0042")
_TAIL_RE = re.compile(r"^[A-Z]+-(\d{6})-(\d+)$")


def generate_invoice_number(company: Company, *, when: date | None = None, prefix: str = "INV", width: int = 4) -> str:
    """
    Format: {prefix}-YYYYMM-#### (per company, per month).

    Args:
        company: Company to scope the sequence.
        when:    Date to derive YYYYMM from (default: today in local time).
                 Pass the invoice's issue_date if you want numbering by issue month.
        prefix:  Leading string (default "INV").
        width:   Zero-padding width for the sequence (default 4).

    Returns:
        The next invoice number string, e.g., "INV-202509-0001".
    """
    d = when or timezone.localdate()
    head = f"{prefix}-{d:%Y%m}"

    # Grab the most recent number for this company+month (string sort is OK with zero-padding)
    last_num = (
        Invoice.objects
        .filter(company=company, number__startswith=head)
        .order_by("-number")
        .values_list("number", flat=True)
        .first()
    )

    if last_num:
        # Prefer regex; fall back to rsplit for robustness
        m = _TAIL_RE.match(last_num)
        try:
            seq = int(m.group(2)) + 1 if m else int(str(last_num).rsplit("-", 1)[-1]) + 1
        except Exception:
            seq = 1
    else:
        seq = 1

    return f"{head}-{seq:0{width}d}"


def allocate_invoice_number(company: Company, *, when: date | None = None, prefix: str = "INV", width: int = 4, max_retries: int = 5) -> str:
    """
    Best-effort allocator that retries on conflicts. Useful if you see occasional
    IntegrityError from the unique (company, number) constraint under concurrency.
    """
    for _ in range(max_retries):
        number = generate_invoice_number(company, when=when, prefix=prefix, width=width)
        try:
            with transaction.atomic():
                # Fast existence check inside a txn; caller should insert immediately after returning this value.
                if Invoice.objects.filter(company=company, number=number).exists():
                    continue
                return number
        except IntegrityError:
            # Very rare; loop and try again
            continue
    raise RuntimeError("Could not allocate a unique invoice number after retries")
