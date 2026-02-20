"""Template helpers for the public pricing page.

IMPORTANT:
Never compare plan codes lexicographically (e.g. "premium" > "starter").
Always use the billing tier rank rules defined in `billing.services`.
"""

from django import template

from billing.services import plan_meets

register = template.Library()


@register.filter(name="has_feature")
def has_feature(plan_code: str, min_plan: str) -> bool:
    """Return True when `plan_code` meets or exceeds `min_plan`."""

    try:
        return bool(plan_meets(str(plan_code), min_plan=str(min_plan)))
    except Exception:
        # Be safe in templates; unknown values should behave as "not included".
        return False
