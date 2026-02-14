from __future__ import annotations

from django.conf import settings

from companies.permissions import is_admin, is_manager, is_owner
from companies.services import get_active_company, get_active_employee_profile, user_companies_qs

from billing.services import build_subscription_summary
from core.support_mode import get_support_mode
from core.onboarding import build_onboarding_checklist_fast, onboarding_progress


def app_context(request):
    """
    Global template context for authenticated app pages (and a small public subset).

    Note: We intentionally expose a minimal set of "public" settings so public templates
    can render correctly without duplicating context processors.
    """
    public = {
        "SITE_NAME": getattr(settings, "SITE_NAME", "EZ360PM"),
        "RECAPTCHA_ENABLED": getattr(settings, "RECAPTCHA_ENABLED", False),
        "RECAPTCHA_SITE_KEY": getattr(settings, "RECAPTCHA_SITE_KEY", ""),
    }

    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {
            **public,
            "active_company": None,
            "active_employee": None,
            "user_companies": [],
        }

    active_company = get_active_company(request)
    active_employee = get_active_employee_profile(request)

    sub_summary = build_subscription_summary(active_company) if active_company else None

    onboarding = None
    if active_company:
        try:
            steps = build_onboarding_checklist_fast(active_company)
            onboarding = onboarding_progress(steps)
        except Exception:
            onboarding = None

    return {
        **public,
        "active_company": active_company,
        "active_employee": active_employee,
        "user_companies": list(user_companies_qs(request.user).order_by("name")),
        "is_manager": is_manager(active_employee),
        "is_admin": is_admin(active_employee),
        "is_owner": is_owner(active_employee),
        "subscription_summary": sub_summary,
        "onboarding_progress_nav": onboarding,
    }
