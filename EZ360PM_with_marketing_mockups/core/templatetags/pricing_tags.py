from __future__ import annotations

from django import template

from billing.services import plan_meets

register = template.Library()


@register.filter(name="has_feature")
def has_feature(plan_code: str, min_plan: str) -> bool:
    """Return True if the given plan includes a feature whose minimum tier is min_plan."""
    return bool(plan_meets(str(plan_code), min_plan=str(min_plan)))
