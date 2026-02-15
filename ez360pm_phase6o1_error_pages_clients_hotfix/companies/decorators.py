from __future__ import annotations

from functools import wraps
from typing import Callable, TypeVar

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from core.support_mode import get_support_mode
from accounts.services_2fa import is_session_2fa_verified

from .models import EmployeeRole
from .permissions import has_min_role
from .services import ensure_active_company_for_user, get_active_company, get_active_employee_profile

F = TypeVar("F", bound=Callable[..., HttpResponse])


def company_context_required(view_func: F) -> F:
    """Ensure the request has an active company + employee profile.

    Support Mode exception:
    - If the current user is staff AND support mode is active, we allow access without being an employee.
      (A lightweight employee proxy is provided by companies.services.get_active_employee_profile.)
    """

    @login_required
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        if not ensure_active_company_for_user(request):
            return redirect("companies:onboarding")

        company = get_active_company(request)
        employee = get_active_employee_profile(request)

        if not company:
            return redirect("companies:switch")

        support = get_support_mode(request)
        if not employee and not (support.is_active and getattr(request.user, "is_staff", False)):
            messages.error(request, "You are not an employee of the selected company.")
            return redirect("companies:switch")

        request.active_company = company
        request.active_employee = employee

        # -----------------------------
        # 2FA enforcement (Hardening Phase 1)
        #
        # Policy:
        # - Always require 2FA for company Admin/Owner roles.
        # - Additionally require 2FA if company flags indicate so.
        # - Employee.force_2fa always wins.
        #
        # We enforce as a step-up challenge on company-scoped pages.
        # -----------------------------
        try:
            role = getattr(employee, "role", None)
            require_admin_owner = role in {EmployeeRole.ADMIN, EmployeeRole.OWNER}
            require_company_all = bool(getattr(company, "require_2fa_for_all", False))
            require_company_admin_mgr = bool(getattr(company, "require_2fa_for_admins_managers", False)) and role in {
                EmployeeRole.MANAGER,
                EmployeeRole.ADMIN,
                EmployeeRole.OWNER,
            }
            require_employee = bool(getattr(employee, "force_2fa", False))

            requires_2fa = bool(require_admin_owner or require_company_all or require_company_admin_mgr or require_employee)

            if requires_2fa and not is_session_2fa_verified(request):
                tf = getattr(getattr(request, "user", None), "two_factor", None)
                if not tf or not getattr(tf, "is_enabled", False):
                    messages.info(request, "Two-factor authentication is required. Please enable it to continue.")
                    return redirect("accounts:two_factor_setup")
                messages.info(request, "Two-factor authentication is required. Please confirm your code.")
                return redirect("accounts:two_factor_confirm")
        except Exception:
            # Never break app access due to 2FA policy evaluation.
            pass

        return view_func(request, *args, **kwargs)

    return _wrapped  # type: ignore[misc]


def require_min_role(min_role: str):
    """Decorator: require an employee role at least min_role."""

    def decorator(view_func: F) -> F:
        @company_context_required
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args, **kwargs):
            employee = getattr(request, "active_employee", None)
            # In support mode, employee may be a lightweight object with role="owner"
            if not has_min_role(employee, min_role):
                messages.error(request, "You do not have permission to access that page.")
                return redirect("core:app_dashboard")
            return view_func(request, *args, **kwargs)

        return _wrapped  # type: ignore[misc]

    return decorator
