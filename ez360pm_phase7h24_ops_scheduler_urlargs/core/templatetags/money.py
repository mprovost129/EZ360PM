from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django import template

register = template.Library()


@register.filter
def money_cents(value) -> str:
    """Format an integer cents amount as $x,xxx.xx."""
    try:
        cents = int(value or 0)
    except Exception:
        cents = 0
    dollars = (Decimal(cents) / Decimal('100')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    # Use Python formatting for commas
    return f"${dollars:,.2f}"


@register.filter
def money(value) -> str:
    """Alias for money_cents (format integer cents as $x,xxx.xx)."""
    return money_cents(value)
