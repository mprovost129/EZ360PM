from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP


def format_money_cents(value) -> str:
    """Format integer cents as $x,xxx.xx (safe for None/invalid)."""
    try:
        cents = int(value or 0)
    except Exception:
        cents = 0
    dollars = (Decimal(cents) / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"${dollars:,.2f}"
