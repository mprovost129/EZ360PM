# expenses/services.py
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Iterable, Optional, List, Dict, Any

from .models import Expense


TWOPLACES = Decimal("0.01")
HUNDRED = Decimal("100.00")


def _q2(value: Decimal) -> Decimal:
    """Round to cents using bankers-friendly HALF_UP."""
    try:
        return value.quantize(TWOPLACES, rounding=ROUND_HALF_UP)
    except (InvalidOperation, AttributeError, TypeError):
        return Decimal("0.00")


def _as_decimal(value: object, default: str = "0.00") -> Decimal:
    """Best-effort conversion to Decimal with safe default."""
    try:
        return Decimal(str(value))
    except Exception:
        return Decimal(default)


def _expense_price(amount: Decimal, markup_pct: Optional[Decimal], *, billable: bool) -> Decimal:
    """
    Compute the rebill price for a single expense.
    - If not billable, returns the base amount (rounded to cents).
    - If billable, applies `markup_pct` (e.g., 10.00 → +10%) then rounds.
    """
    amt = _as_decimal(amount)
    if not billable:
        return _q2(amt)

    pct = _as_decimal(markup_pct or Decimal("0.00")) / HUNDRED
    return _q2(amt * (Decimal("1.00") + pct))


def _group_expenses(
    qs: Iterable[Expense],
    group_by: str,
    override_markup_pct: Optional[Decimal],
    label_prefix: str = "",
) -> List[Dict[str, Any]]:
    """
    Group expenses and compute rebilled totals.

    Args:
        qs: Iterable of Expense (QuerySet or list).
        group_by: "category" | "vendor" | "expense" | anything else → "all"
        override_markup_pct: If provided, use this markup % for all billable rows.
        label_prefix: Optional prefix added to each group label.

    Returns:
        List[{"label": str, "total": Decimal, "items": list[Expense]}], sorted by label.
    """
    buckets: Dict[object, List[Expense]] = defaultdict(list)

    for e in qs:
        if group_by == "category":
            key = e.category or "Uncategorized"
        elif group_by == "vendor":
            key = e.vendor or "Unknown vendor"
        elif group_by == "expense":
            key = e.id  # type: ignore # one bucket per expense row
        else:
            key = "all"
        buckets[key].append(e)

    out: List[Dict[str, Any]] = []

    for key, rows in buckets.items():
        total = Decimal("0.00")

        # Sum the rebill price per row, respecting billable flag and optional override markup
        for r in rows:
            base = _as_decimal(r.amount, "0.00")
            markup = override_markup_pct if override_markup_pct is not None else r.billable_markup_pct
            price = _expense_price(base, markup, billable=bool(r.is_billable))
            total += price

        # Human-friendly labels
        if group_by == "expense" and len(rows) == 1:
            e = rows[0]
            base_label = e.description or e.vendor or e.category or "Expense"
            label = f"{base_label}"
        elif group_by in ("category", "vendor"):
            label = f"Expenses — {key}"
        else:
            label = "Expenses"

        if label_prefix:
            label = f"{label_prefix.strip()} — {label}"

        out.append({"label": label, "total": _q2(total), "items": rows})

    # Sort predictably by label
    out.sort(key=lambda x: str(x["label"]))
    return out
