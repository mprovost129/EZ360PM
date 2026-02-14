from __future__ import annotations

from decimal import Decimal

from django import template

register = template.Library()


@register.filter
def minutes_to_hhmm(minutes: int) -> str:
    try:
        m = int(minutes or 0)
    except Exception:
        m = 0
    h = m // 60
    mm = m % 60
    return f"{h}h {mm:02d}m"


@register.filter
def cents_to_dollars(cents: int) -> str:
    try:
        c = int(cents or 0)
    except Exception:
        c = 0
    v = (Decimal(c) / Decimal('100')).quantize(Decimal('0.01'))
    return f"${v}"
