# core/templatetags/subscription_tags.py
from __future__ import annotations

from django import template

from company.utils import get_active_company

try:
    from core.utils import user_has_active_subscription  # type: ignore
except Exception:  # pragma: no cover
    def user_has_active_subscription(company) -> bool:  # fallback
        return False


register = template.Library()


@register.simple_tag(takes_context=True)
def has_subscription(context) -> bool:
    """
    Template tag: {% has_subscription as flag %}
    Returns True if the active company has an active/trialing subscription.
    """
    try:
        req = context.get("request")
        if not req:
            return False
        company = get_active_company(req)
        return bool(company and user_has_active_subscription(company))
    except Exception:
        return False
