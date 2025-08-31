from django import template
from core.utils import get_active_company
from billing.utils import company_has_feature

register = template.Library()

@register.simple_tag(takes_context=True)
def feature_enabled(context, key):
    company = get_active_company(context["request"])
    return company_has_feature(company, key)