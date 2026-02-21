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


@register.filter
def doc_status_badge_class(status: str) -> str:
    """Map document status to a consistent Bootstrap badge class."""
    s = (status or "").strip().lower()
    mapping = {
        "draft": "bg-secondary",
        "sent": "bg-info",
        "accepted": "bg-success",
        "declined": "bg-danger",
        "partially_paid": "bg-warning text-dark",
        "paid": "bg-success",
        "void": "bg-dark",
    }
    return mapping.get(s, "bg-light text-dark")
