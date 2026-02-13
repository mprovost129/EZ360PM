from __future__ import annotations

from dataclasses import dataclass

from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

from billing.services import company_is_locked
from companies.services import get_active_company

import uuid

from .request_context import set_request_id


@dataclass(frozen=True)
class _Allowlist:
    prefix: str


class SubscriptionLockMiddleware(MiddlewareMixin):
    """Lock CRM routes when trial expires and subscription is inactive.

    v1 rule: If the active company's subscription is inactive and trial expired,
    only allow a small set of routes (dashboard/profile/billing/company switch/logout/admin).
    """

    # Prefix-based allowlist (keep small and explicit)
    ALLOW_PREFIXES = [
        _Allowlist("/accounts/"),
        _Allowlist("/billing/"),
        _Allowlist("/companies/switch"),
        _Allowlist("/companies/switch/"),
        _Allowlist("/companies/switch/set/"),
        _Allowlist("/app/"),
        _Allowlist("/admin/"),
        _Allowlist("/api/"),
        _Allowlist("/static/"),
        _Allowlist("/media/"),
    ]

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        path = request.path or "/"
        for item in self.ALLOW_PREFIXES:
            if path.startswith(item.prefix):
                return None

        company = get_active_company(request)
        if not company:
            return None

        if not company_is_locked(company):
            return None

        messages.error(request, "Your trial has ended. Please update billing to continue using EZ360PM.")
        return redirect("billing:locked")


class RequestIDMiddleware:
    """Attach a request id to each request/response for traceability."""

    header_name = "X-Request-ID"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = request.META.get("HTTP_X_REQUEST_ID") or str(uuid.uuid4())
        request.request_id = rid
        set_request_id(rid)
        response = self.get_response(request)
        try:
            response[self.header_name] = rid
        except Exception:
            pass
        return response


from django.conf import settings
from companies.services import get_active_employee_profile
from companies.models import EmployeeRole


class EmailVerificationGateMiddleware(MiddlewareMixin):
    """Allow login, but gate access to company features until email is verified."""

    ALLOW_PREFIXES = [
        _Allowlist("/accounts/"),
        _Allowlist("/admin/"),
        _Allowlist("/static/"),
        _Allowlist("/media/"),
        _Allowlist("/health/"),
    ]

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        if not getattr(settings, "ACCOUNTS_REQUIRE_EMAIL_VERIFICATION", False):
            return None

        if getattr(user, "email_verified", False):
            return None

        path = request.path or "/"
        for item in self.ALLOW_PREFIXES:
            if path.startswith(item.prefix):
                return None

        return redirect("accounts:verify_required")


class TwoFactorEnforcementMiddleware(MiddlewareMixin):
    """Enforce 2FA for privileged roles, with a one-session grace period."""

    ALLOW_PREFIXES = [
        _Allowlist("/accounts/2fa/"),
        _Allowlist("/accounts/logout"),
        _Allowlist("/accounts/logout/"),
        _Allowlist("/accounts/verify"),
        _Allowlist("/accounts/verify-"),
        _Allowlist("/static/"),
        _Allowlist("/media/"),
        _Allowlist("/admin/"),
        _Allowlist("/health/"),
    ]

    GRACE_SESSION_KEY = "two_factor_grace_used"

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        path = request.path or "/"
        for item in self.ALLOW_PREFIXES:
            if path.startswith(item.prefix):
                return None

        emp = get_active_employee_profile(request)
        if not emp:
            return None

        is_enabled = hasattr(user, "two_factor") and user.two_factor.is_enabled

        requires = False
        if user.is_staff and emp.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER}:
            requires = True
        else:
            company = emp.company
            if getattr(emp, "force_2fa", False):
                requires = True
            elif getattr(company, "require_2fa_for_admins_managers", False) and emp.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER}:
                requires = True
            elif getattr(company, "require_2fa_for_all", False):
                requires = True

        if not requires:
            return None
        if is_enabled:
            return None

        if not request.session.get(self.GRACE_SESSION_KEY):
            request.session[self.GRACE_SESSION_KEY] = True
            messages.warning(request, "For security, you must enable two-factor authentication. Please set it up now.")
            return None

        messages.error(request, "Two-factor authentication is required for your role. Please set it up to continue.")
        return redirect("accounts:two_factor_setup")


class SecurityHeadersMiddleware:
    """Attach security headers (prod-safe defaults). CSP defaults to report-only unless enforced."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        response.setdefault("X-Content-Type-Options", "nosniff")
        response.setdefault("X-Frame-Options", "DENY")
        response.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")

        if getattr(settings, "SECURE_HSTS_SECONDS", 0):
            response.setdefault(
                "Strict-Transport-Security",
                f"max-age={int(settings.SECURE_HSTS_SECONDS)}; includeSubDomains",
            )

        csp = getattr(settings, "SECURE_CSP", "")
        csp_report_only = getattr(settings, "SECURE_CSP_REPORT_ONLY", True)
        csp_header_value = ""
        if isinstance(csp, dict):
            # Convert dict to CSP string
            csp_header_value = "; ".join(
                f"{k} {' '.join(v)}" for k, v in csp.items()
            )
        elif isinstance(csp, str):
            csp_header_value = csp.strip()
        if csp_header_value:
            header = "Content-Security-Policy-Report-Only" if csp_report_only else "Content-Security-Policy"
            response.setdefault(header, csp_header_value)

        return response


from .support_mode import get_support_mode, clear_support_mode


class SupportModeMiddleware(MiddlewareMixin):
    """Ensure support mode expiry is enforced and session is consistent."""

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None
        state = get_support_mode(request)
        if not state.is_active:
            return None
        # If a non-staff user somehow has support mode keys, clear it.
        if not getattr(user, "is_staff", False):
            clear_support_mode(request)
            return None
        return None


class SupportModeReadOnlyMiddleware(MiddlewareMixin):
    """Block mutating requests while in support mode.

    Support mode is for diagnosis and assistance, not making changes on behalf of customers.
    """

    ALLOW_PREFIXES = [
        _Allowlist("/support/"),
        _Allowlist("/accounts/logout"),
        _Allowlist("/accounts/logout/"),
        _Allowlist("/admin/"),
        _Allowlist("/static/"),
        _Allowlist("/media/"),
        _Allowlist("/health/"),
    ]

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated or not getattr(user, "is_staff", False):
            return None

        state = get_support_mode(request)
        if not state.is_active:
            return None

        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            path = request.path or "/"
            for item in self.ALLOW_PREFIXES:
                if path.startswith(item.prefix):
                    return None
            messages.error(request, "Support mode is read-only. Exit support mode to make changes.")
            return redirect("core:support_mode_status")
        return None
