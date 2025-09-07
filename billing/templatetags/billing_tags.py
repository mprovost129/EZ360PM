# billing/templatetags/billing_tags.py
from __future__ import annotations

from django import template
from company.utils import get_active_company
from billing.utils import company_has_feature

register = template.Library()


@register.simple_tag(takes_context=True)
def feature_enabled(context, key: str, default: bool = False) -> bool:
    """
    Template tag: return True if the active company has an active subscription
    and the tier enables the given feature `key`.

    Usage:
        {% load billing_tags %}
        {% feature_enabled "estimates" as has_estimates %}
        {% if has_estimates %}
            ... show estimates UI ...
        {% endif %}
    """
    request = context.get("request")
    if not request:
        return default
    company = get_active_company(request)
    return company_has_feature(company, key)
