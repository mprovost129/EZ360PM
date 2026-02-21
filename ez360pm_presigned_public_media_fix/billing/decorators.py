from __future__ import annotations

from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from companies.models import EmployeeRole
from companies.services import get_active_company, get_active_employee_profile

from .models import PlanCode
from .services import build_subscription_summary, plan_allows_feature, plan_meets


def require_company_admin(view_func):
    """Billing is company-scoped; require an active company and admin+ role."""

    @login_required
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        company = get_active_company(request)
        if not company:
            return redirect("companies:switch")

        employee = get_active_employee_profile(request)
        if not employee or employee.role not in {EmployeeRole.ADMIN, EmployeeRole.OWNER}:
            messages.error(request, "Admin access required.")
            return redirect("core:app_dashboard")

        return view_func(request, *args, **kwargs)

    return _wrapped


def require_staff(view_func):
    """Restrict a view to Django staff/superusers (used for Stripe webhook history/debugging)."""

    @login_required
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
        user = getattr(request, "user", None)
        if not user or not (user.is_staff or user.is_superuser):
            messages.error(request, "Staff access required.")
            return redirect("billing:overview")
        return view_func(request, *args, **kwargs)

    return _wrapped


def tier_required(min_plan: str):
    """Gate a view behind a minimum subscription tier."""

    def _decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            company = get_active_company(request)
            if not company:
                return redirect("companies:switch")

            summary = build_subscription_summary(company)
            if not summary.is_active_or_trial:
                messages.error(request, "Your subscription is inactive. Please update billing to continue.")
                return redirect("billing:overview")

            if not plan_meets(summary.plan, min_plan=min_plan):
                if min_plan == PlanCode.PROFESSIONAL:
                    msg = "That feature is available on Professional and Premium."
                elif min_plan == PlanCode.PREMIUM:
                    msg = "That feature is available on Premium."
                else:
                    msg = "That feature is not available on your plan."
                messages.info(request, msg)
                return redirect("billing:overview")

            return view_func(request, *args, **kwargs)

        return _wrapped

    return _decorator


def feature_required(feature_code: str, *, min_plan_hint: str | None = None):
    """Gate a view behind a plan feature code."""

    def _decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs) -> HttpResponse:
            company = get_active_company(request)
            if not company:
                return redirect("companies:switch")

            summary = build_subscription_summary(company)
            if not summary.is_active_or_trial:
                messages.error(request, "Your subscription is inactive. Please update billing to continue.")
                return redirect("billing:overview")

            if not plan_allows_feature(summary.plan, feature_code):
                # Friendly message
                hint = min_plan_hint
                if hint == PlanCode.PROFESSIONAL:
                    messages.info(request, "That feature is available on Professional and Premium.")
                elif hint == PlanCode.PREMIUM:
                    messages.info(request, "That feature is available on Premium.")
                else:
                    messages.info(request, "That feature is not available on your plan.")
                return redirect("billing:overview")

            return view_func(request, *args, **kwargs)

        return _wrapped

    return _decorator
