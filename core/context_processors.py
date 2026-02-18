from __future__ import annotations

from urllib.parse import urlencode

from django.conf import settings

from companies.permissions import is_admin, is_manager, is_owner
from companies.services import get_active_company, get_active_employee_profile, user_companies_qs

from billing.services import build_subscription_summary
from core.support_mode import get_support_mode
from core.onboarding import build_onboarding_checklist_fast, onboarding_progress


def _timer_context(request, active_company, active_employee):
    """Small, safe timer context used by the navbar dropdown.

    This must never hard-fail template rendering. If we can't load timer state
    (migrations drifting, missing tables, etc.), we still render the form shell
    so the UI doesn't look "broken" – and we surface a short reason.
    """
    if not active_company or not active_employee:
        return {
            "timer_state": None,
            "timer_running": False,
            "timer_elapsed": "",
            "timer_total_seconds": 0,
            "timer_form": None,
            "can_manage_catalog": False,
            "timer_unavailable_reason": "Timer unavailable (missing company/employee context).",
        }

    # Permissions (used for catalog helper link and optional "save service" checkbox).
    # companies.permissions helpers operate on EmployeeProfile (role hierarchy)
    can_manage_catalog = bool(is_owner(active_employee) or is_admin(active_employee) or is_manager(active_employee))

    # Always try to render a valid form – even if state fetch fails.
    try:
        from django.utils import timezone
        from timetracking.models import TimerState
        from timetracking.forms import TimerStartForm

        timer_state, _ = TimerState.objects.get_or_create(company=active_company, employee=active_employee)
        timer_running = bool(timer_state.is_running and (timer_state.started_at or timer_state.elapsed_seconds))

        now = timezone.now()
        total_seconds = 0
        elapsed = ""

        if timer_running:
            total_seconds = int(timer_state.elapsed_seconds or 0)
            if timer_state.started_at and not getattr(timer_state, "is_paused", False):
                delta = now - timer_state.started_at
                total_seconds += max(0, int(delta.total_seconds()))

            mins = total_seconds // 60
            hrs = mins // 60
            rem = mins % 60
            elapsed = f"{hrs}h {rem:02d}m" if hrs else f"{rem}m"

        timer_form = TimerStartForm(
            company=active_company,
            can_manage_catalog=can_manage_catalog,
            initial={
                "project": timer_state.project_id,
                "service_catalog_item": timer_state.service_catalog_item_id,
                "service_name": timer_state.service_name,
                "note": timer_state.note,
            },
        )

        return {
            "timer_state": timer_state,
            "timer_running": timer_running,
            "timer_elapsed": elapsed,
            "timer_total_seconds": total_seconds,
            "timer_form": timer_form,
            "can_manage_catalog": can_manage_catalog,
            "timer_unavailable_reason": "",
        }
    except Exception:
        # Fall back to a blank form shell so navbar still shows Project/Service/Notes.
        try:
            from timetracking.forms import TimerStartForm

            timer_form = TimerStartForm(company=active_company, can_manage_catalog=can_manage_catalog)
        except Exception:
            timer_form = None

        return {
            "timer_state": None,
            "timer_running": False,
            "timer_elapsed": "",
            "timer_total_seconds": 0,
            "timer_form": timer_form,
            "can_manage_catalog": can_manage_catalog,
            "timer_unavailable_reason": "Timer unavailable (timer state not ready).",
        }


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

    ctx = {
        **public,
        "active_company": active_company,
        "active_employee": active_employee,
        "user_companies": list(user_companies_qs(request.user).order_by("name")),
        "is_manager": is_manager(active_employee),
        "is_admin": is_admin(active_employee),
        "is_owner": is_owner(active_employee),
        "subscription_summary": sub_summary,
        "onboarding_progress_nav": onboarding,
        **_timer_context(request, active_company, active_employee),
    }

    # Staff-only: quick “Report QA issue” link that pre-fills the QA form with the current URL.
    # This supports the Phase 8Y QA burn-down workflow without impacting non-staff UX.
    try:
        if request.user.is_staff:
            path = (getattr(request, "path", "") or "").strip() or "/"
            area_guess = path.strip("/").split("/")[0][:64] if path.strip("/") else ""
            params = {
                "related_url": request.build_absolute_uri(),
                "area": area_guess,
            }
            if active_company:
                params["company"] = str(active_company.pk)
            ctx["qa_report_href"] = f"/ops/qa/new/?{urlencode(params)}"
    except Exception:
        # Never break template rendering for a convenience feature.
        pass

    return ctx
