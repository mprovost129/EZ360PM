from __future__ import annotations

from dataclasses import dataclass
import logging
import time
import random

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from django.db import connection

from billing.services import company_is_locked
from companies.services import get_active_company

import uuid

from .request_context import set_request_id


logger_perf = logging.getLogger("ez360pm.perf")


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



class CompanySuspensionMiddleware(MiddlewareMixin):
    """Lock tenant routes when a company is suspended by staff."""

    ALLOW_PREFIXES = [
        _Allowlist("/accounts/"),
        _Allowlist("/billing/"),
        _Allowlist("/companies/switch"),
        _Allowlist("/companies/switch/"),
        _Allowlist("/companies/switch/set/"),
        _Allowlist("/ops/"),
        _Allowlist("/admin/"),
        _Allowlist("/api/"),
        _Allowlist("/static/"),
        _Allowlist("/media/"),
    ]

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        # Staff in support mode can still access tenant pages to investigate/fix.
        try:
            support = getattr(request, "support_mode", None)
            if support and getattr(support, "is_active", False) and getattr(user, "is_staff", False):
                return None
        except Exception:
            pass

        path = request.path or "/"
        for item in self.ALLOW_PREFIXES:
            if path.startswith(item.prefix):
                return None

        company = get_active_company(request)
        if not company:
            return None

        if not getattr(company, "is_active", True) or getattr(company, "is_suspended", False):
            messages.error(request, "This company account is currently suspended. Please contact support.")
            return redirect("companies:account_suspended")

        return None


class ForceLogoutMiddleware(MiddlewareMixin):
    """Force user logout when staff sets User.force_logout_at."""

    AUTH_TIME_KEY = "auth_time_iso"

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        force_at = getattr(user, "force_logout_at", None)
        if not force_at:
            return None

        auth_iso = request.session.get(self.AUTH_TIME_KEY)
        if not auth_iso:
            # No marker => treat as stale and force re-auth
            from django.contrib.auth import logout
            logout(request)
            messages.info(request, "Please sign in again to continue.")
            return redirect("accounts:login")

        try:
            from django.utils.dateparse import parse_datetime
            auth_dt = parse_datetime(str(auth_iso))
        except Exception:
            auth_dt = None

        if not auth_dt or auth_dt < force_at:
            from django.contrib.auth import logout
            logout(request)
            messages.info(request, "Please sign in again to continue.")
            return redirect("accounts:login")

        return None
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


class PerformanceLoggingMiddleware:
    """Lightweight request/query timing logger (dev/staging friendly).

    Enabled via settings.EZ360_PERF_LOGGING_ENABLED.

    Logs:
      - slow requests over EZ360_PERF_REQUEST_MS
      - slow ORM queries over EZ360_PERF_QUERY_MS

    Notes:
      - Uses connection.queries (DEBUG required to populate).
      - Safe to keep installed in dev only.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        from django.conf import settings

        enabled = bool(getattr(settings, "EZ360_PERF_LOGGING_ENABLED", False))
        if not enabled:
            return self.get_response(request)

        request_ms = int(getattr(settings, "EZ360_PERF_REQUEST_MS", 600))
        query_ms = int(getattr(settings, "EZ360_PERF_QUERY_MS", 120))
        top_n = int(getattr(settings, "EZ360_PERF_TOP_N", 5))
        sample_rate = float(getattr(settings, "EZ360_PERF_SAMPLE_RATE", 1.0) or 0.0)
        store_db = bool(getattr(settings, "EZ360_PERF_STORE_DB", False))

        t0 = time.perf_counter()
        # Reset per-request query log (best-effort)
        try:
            if hasattr(connection, "queries_log"):
                connection.queries_log.clear()  # type: ignore[attr-defined]
        except Exception:
            pass

        response = self.get_response(request)
        dt_ms = (time.perf_counter() - t0) * 1000.0

        # Collect query timings
        slow_queries = []
        total_queries = 0
        try:
            queries = list(getattr(connection, "queries", []) or [])
            total_queries = len(queries)
            for q in queries:
                # Django stores seconds as string
                raw = q.get("time")
                try:
                    q_ms = float(raw) * 1000.0
                except Exception:
                    q_ms = 0.0
                if q_ms >= query_ms:
                    sql = (q.get("sql") or "").strip().replace("\n", " ")
                    slow_queries.append((q_ms, sql))
            slow_queries.sort(key=lambda x: x[0], reverse=True)
        except Exception:
            slow_queries = []

        path = (request.path or "/")
        method = getattr(request, "method", "?")
        status = getattr(response, "status_code", "?")

        is_slow = bool(dt_ms >= request_ms or slow_queries)

        if is_slow:
            logger_perf.warning(
                "PERF %s %s %s in %.1fms (%s queries)",
                method,
                path,
                status,
                dt_ms,
                total_queries,
            )

            for ms, sql in slow_queries[: max(1, top_n)]:
                logger_perf.warning("  SLOW SQL %.1fms: %s", ms, sql[:900])

            # Optional: store a staff-visible ops alert (sampled)
            try:
                if store_db and sample_rate > 0 and random.random() <= min(1.0, max(0.0, sample_rate)):
                    from ops.services_alerts import create_ops_alert
                    from ops.models import OpsAlertLevel, OpsAlertSource

                    create_ops_alert(
                        title="Slow request",
                        message=f"{method} {path} returned {status} in {dt_ms:.1f}ms",
                        level=OpsAlertLevel.WARN,
                        source=OpsAlertSource.SLOW_REQUEST,
                        company=get_active_company(request),
                        details={
                            "method": method,
                            "path": path,
                            "status": int(status) if str(status).isdigit() else str(status),
                            "duration_ms": float(f"{dt_ms:.1f}"),
                            "query_count": int(total_queries),
                        },
                    )
            except Exception:
                pass

        return response

from companies.services import get_active_employee_profile
from companies.models import EmployeeRole



class MaintenanceModeMiddleware:
    """If maintenance mode is enabled, show a 503 maintenance page to non-staff users.

    This is a launch/ops safety switch. It is intentionally tolerant of missing tables
    (fresh DBs / migrations not yet applied) to avoid breaking the site.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest):
        # Always allow static/media, health checks, and error pages to render.
        path = getattr(request, "path", "") or ""
        if path.startswith("/static/") or path.startswith("/media/") or path.startswith("/favicon"):
            return self.get_response(request)

        # Allow ops probe endpoints to work even during maintenance.
        if path.startswith("/ops/probe"):
            return self.get_response(request)

        # Load maintenance settings lazily to avoid import-time DB touches.
        try:
            from ops.models import SiteConfig  # local import to avoid circular deps
        except Exception:
            return self.get_response(request)

        try:
            cfg = SiteConfig.get_solo()
        except Exception:
            # Table may not exist yet (fresh DB) or migrations pending.
            return self.get_response(request)

        if not getattr(cfg, "maintenance_mode_enabled", False):
            return self.get_response(request)

        # Allow staff through (optional).
        user = getattr(request, "user", None)
        if getattr(cfg, "maintenance_allow_staff", True) and getattr(user, "is_authenticated", False) and getattr(user, "is_staff", False):
            return self.get_response(request)

        # If the user isn't staff, show the maintenance page.
        from django.shortcuts import render

        context = {
            "maintenance_message": (getattr(cfg, "maintenance_message", "") or "").strip(),
        }
        response = render(request, "maintenance.html", context=context, status=503)
        return response


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
    """Enforce 2FA only when company/employee policy requires it, with a one-session grace period."""

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
        company = emp.company

        # Admin-configurable enforcement only. No implicit role-based forcing.
        if getattr(emp, "force_2fa", False):
            requires = True
        elif getattr(company, "require_2fa_for_all", False):
            requires = True
        elif getattr(company, "require_2fa_for_admins_managers", False) and emp.role in {EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER}:
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


class UserPresenceMiddleware(MiddlewareMixin):
    """Record lightweight user presence for staff SLO dashboards.

    Best-effort and throttled per-session to avoid DB churn.
    """

    SESSION_KEY = "presence_last_ping_ts"
    MIN_SECONDS_BETWEEN_WRITES = 60

    ALLOW_PREFIXES = [
        _Allowlist("/static/"),
        _Allowlist("/media/"),
        _Allowlist("/healthz"),
        _Allowlist("/healthz/"),
        _Allowlist("/admin/"),
    ]

    def process_request(self, request: HttpRequest):
        user = getattr(request, "user", None)
        if not user or not user.is_authenticated:
            return None

        path = request.path or "/"
        for item in self.ALLOW_PREFIXES:
            if path.startswith(item.prefix):
                return None

        # Only record presence when a company context exists.
        company = get_active_company(request)
        if not company:
            return None

        now_ts = int(time.time())
        last_ts = int(request.session.get(self.SESSION_KEY) or 0)
        if last_ts and (now_ts - last_ts) < self.MIN_SECONDS_BETWEEN_WRITES:
            return None

        request.session[self.SESSION_KEY] = now_ts

        try:
            from django.utils import timezone
            from ops.models import UserPresence

            UserPresence.touch(user=user, company=company, when=timezone.now())
        except Exception:
            # Presence is best-effort; never break requests.
            return None

        return None


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



class ScannerShieldMiddleware(MiddlewareMixin):
    """Fast-path 404/410 for common internet scanner endpoints.

    Render logs get noisy from bots probing for known paths (e.g. /webhook-test, /.env).
    This middleware short-circuits those requests before URL resolution and view execution.

    We intentionally keep this conservative: only obviously malicious/probe paths.
    """

    # Prefixes are matched case-sensitively against request.path.
    BLOCK_PREFIXES = (
        "/webhook-test",
        "/.env",
        "/.git",
        "/wp-admin",
        "/wp-login",
        "/xmlrpc.php",
        "/phpmyadmin",
        "/pma",
        "/cgi-bin",
        "/vendor/phpunit",
    )

    # Exact paths that are common probes.
    BLOCK_EXACT = (
        "/.env",
        "/.git/config",
        "/.git/HEAD",
    )

    def process_request(self, request: HttpRequest):
        path = request.path or "/"

        # Never block static/media; let whitenoise/storage handle.
        if path.startswith(settings.STATIC_URL) or path.startswith(getattr(settings, "MEDIA_URL", "/media/")):
            return None

        if path in self.BLOCK_EXACT:
            from django.http import HttpResponseGone
            return HttpResponseGone("Gone")

        for pref in self.BLOCK_PREFIXES:
            if path.startswith(pref):
                # 404 is fine; 410 is also acceptable. Use 404 to avoid signaling too much.
                from django.http import HttpResponseNotFound
                return HttpResponseNotFound("Not Found")

        return None


class SentryContextMiddleware:
    """Attach user + company context to Sentry events.

    Safe no-op when Sentry SDK is not installed or not configured.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            import sentry_sdk

            with sentry_sdk.configure_scope() as scope:
                try:
                    scope.set_tag("environment", getattr(settings, "ENVIRONMENT", "") or getattr(settings, "APP_ENVIRONMENT", ""))
                except Exception:
                    pass
                try:
                    release = getattr(settings, "SENTRY_RELEASE", "") or getattr(settings, "RELEASE_SHA", "")
                    if release:
                        scope.set_tag("release", release)
                except Exception:
                    pass

                try:
                    user = getattr(request, "user", None)
                    if user and getattr(user, "is_authenticated", False):
                        scope.set_user({"id": user.pk, "email": getattr(user, "email", "")})
                except Exception:
                    pass

                try:
                    # Best-effort active company detection
                    company = None
                    try:
                        from companies.services import get_active_company

                        company = get_active_company(request)
                    except Exception:
                        company = getattr(request, "company", None)

                    if company and getattr(company, "pk", None):
                        scope.set_context(
                            "company",
                            {
                                "id": str(company.pk),
                                "name": getattr(company, "name", ""),
                            },
                        )
                        scope.set_tag("company_id", str(company.pk))
                except Exception:
                    pass

        except Exception:
            # no sentry, or any other failure
            pass

        return self.get_response(request)
