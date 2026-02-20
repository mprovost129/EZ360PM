from __future__ import annotations

"""Billing/subscription template helpers.

We keep navigation and small UI affordances aligned with plan gating.
The actual authorization is still enforced server-side by decorators.
"""

from django import template

from billing.models import PlanCode
from billing.services import (
    FEATURE_ACCOUNTING_ENGINE,
    FEATURE_DROPBOX,
    plan_allows_feature,
    plan_meets,
)


register = template.Library()


@register.filter
def plan_meets_min(plan: str, min_plan: str) -> bool:
    """Return True if `plan` rank >= `min_plan` rank."""
    try:
        return plan_meets(plan or "", min_plan=min_plan)
    except Exception:
        return False


@register.filter
def is_professional_or_higher(plan: str) -> bool:
    """Convenience filter: Professional+."""
    try:
        return plan_meets(plan or "", min_plan=PlanCode.PROFESSIONAL)
    except Exception:
        return False


@register.filter
def is_premium(plan: str) -> bool:
    """Convenience filter: Premium."""
    try:
        return plan_meets(plan or "", min_plan=PlanCode.PREMIUM)
    except Exception:
        return False


@register.simple_tag
def plan_allows(plan: str, feature_code: str) -> bool:
    """Return True if `plan` allows `feature_code`."""
    try:
        return plan_allows_feature(plan or "", feature_code)
    except Exception:
        return False


@register.simple_tag
def can_use_accounting(plan: str) -> bool:
    """Return True if plan includes the accounting engine (Professional+)."""
    return plan_allows(plan or "", FEATURE_ACCOUNTING_ENGINE)


@register.simple_tag
def can_use_dropbox(plan: str) -> bool:
    """Return True if plan includes Dropbox integration (Premium)."""
    return plan_allows(plan or "", FEATURE_DROPBOX)
