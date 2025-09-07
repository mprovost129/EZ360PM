# dashboard/middleware.py
from __future__ import annotations

from typing import Callable, Iterable
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import resolve, ResolverMatch
from company.utils import get_active_company, get_onboarding_status


class OnboardingRedirectMiddleware:
    """
    Redirect signed-in users from the dashboard home to the onboarding screen
    until onboarding is complete or dismissed.

    Safeguards:
      - Only triggers on safe, non-AJAX/HTMX HTML page loads.
      - Skips known exempt views/routes to prevent loops (incl. onboarding itself).
      - Can be disabled via settings.ONBOARDING_REDIRECT_ENABLED = False.
      - Respects request.session["onboarding_dismissed"].
      - Supports project-specific exemptions via settings.
    """

    # View names to never intercept (namespaced)
    BASE_EXEMPT_VIEW_NAMES: set[str] = {
        "dashboard:onboarding",
        "dashboard:onboarding_dismiss",
        "dashboard:cookie_consent_set",
        "dashboard:cookie_preferences",
        "dashboard:help_index",
        "dashboard:help_article",
        "dashboard:privacy",
        "dashboard:terms",
        "dashboard:contact",
        "dashboard:contact_submit",
        "dashboard:contact_thanks",
    }

    # URL prefixes to skip (paths, NOT names); admin, auth, APIs, static/media, etc.
    BASE_EXEMPT_PREFIXES: tuple[str, ...] = (
        "/admin",
        "/accounts",
        "/api",
        "/static",
        "/media",
        "/favicon.ico",
        "/robots.txt",
        "/sitemap.xml",
        "/.well-known",
        "/healthz",
        "/status",
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.enabled: bool = bool(getattr(settings, "ONBOARDING_REDIRECT_ENABLED", True))

        # Allow settings to extend exemptions
        extra_views: Iterable[str] = getattr(settings, "ONBOARDING_EXEMPT_VIEW_NAMES", [])
        extra_prefixes: Iterable[str] = getattr(settings, "ONBOARDING_EXEMPT_PREFIXES", [])

        self.EXEMPT_VIEW_NAMES: set[str] = set(self.BASE_EXEMPT_VIEW_NAMES) | set(extra_views)
        self.EXEMPT_PREFIXES: tuple[str, ...] = tuple(self.BASE_EXEMPT_PREFIXES) + tuple(extra_prefixes)

    @staticmethod
    def _wants_html(request: HttpRequest) -> bool:
        """
        True if the client is likely navigating a normal HTML page.
        Avoid redirecting JSON/fetch/API calls.
        """
        accept = (request.headers.get("Accept") or "").lower()
        # If no Accept, err on the safe side and assume HTML page load
        return ("text/html" in accept or "*/*" in accept) and "application/json" not in accept

    @staticmethod
    def _is_ajax_or_htmx(request: HttpRequest) -> bool:
        """
        Detect classic AJAX and HTMX requests.
        """
        h = request.headers
        return (
            (h.get("x-requested-with", "").lower() == "xmlhttprequest")
            or (h.get("hx-request", "").lower() == "true")
        )

    def _has_exempt_prefix(self, path: str) -> bool:
        return any(path.startswith(p) for p in self.EXEMPT_PREFIXES)

    def _is_exempt_view(self, match: ResolverMatch | None) -> bool:
        return bool(match and match.view_name in self.EXEMPT_VIEW_NAMES)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Fast-pass if feature is disabled or user is anonymous
        if not self.enabled or not request.user.is_authenticated:
            return self.get_response(request)

        # Only intercept safe, top-level HTML page loads (avoid POST/PUT/PATCH/DELETE, AJAX/HTMX, JSON)
        if request.method not in {"GET", "HEAD"}:
            return self.get_response(request)
        if self._is_ajax_or_htmx(request) or not self._wants_html(request):
            return self.get_response(request)

        # Skip common non-app and system paths early
        if self._has_exempt_prefix(request.path_info):
            return self.get_response(request)

        # Use request.resolver_match if set by earlier middleware; else resolve()
        match = getattr(request, "resolver_match", None)
        if match is None:
            try:
                match = resolve(request.path_info)
            except Exception:
                return self.get_response(request)

        # Only auto-redirect from dashboard home, and never from exempt views
        if match.view_name != "dashboard:home" or self._is_exempt_view(match):
            return self.get_response(request)

        # Respect "onboarding_dismissed"
        if request.session.get("onboarding_dismissed"):
            return self.get_response(request)

        # Compute onboarding status
        company = get_active_company(request)
        status = get_onboarding_status(request.user, company)

        # If incomplete, send to onboarding
        if not status.get("complete"):
            return redirect("dashboard:onboarding")

        # Otherwise, continue as normal
        return self.get_response(request)

