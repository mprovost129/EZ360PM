from __future__ import annotations

from core.money import format_money_cents

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
    """Back-compat money formatter.

    Historically templates used `|cents_to_dollars` for currency output.
    Corporate UI standard is the same formatting used elsewhere: $x,xxx.xx.
    """
    return format_money_cents(cents)
