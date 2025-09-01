# dashboard/middleware.py
from __future__ import annotations

from typing import Callable, Iterable
from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import resolve, ResolverMatch
from core.utils import get_active_company, get_onboarding_status


class OnboardingRedirectMiddleware:
    """
    Redirects signed-in users from the dashboard home to the onboarding screen
    until onboarding is complete or dismissed.

    Safeguards:
      - Only triggers on safe, non-AJAX GET requests.
      - Skips known exempt views/routes to prevent loops (incl. onboarding itself).
      - Can be disabled via settings.ONBOARDING_REDIRECT_ENABLED = False.
      - Respects request.session["onboarding_dismissed"].
    """

    # View names to never intercept (namespaced)
    EXEMPT_VIEW_NAMES: set[str] = {
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
    EXEMPT_PREFIXES: tuple[str, ...] = (
        "/admin",
        "/accounts",
        "/api",
        "/static",
        "/media",
        "/favicon.ico",
        "/robots.txt",
        "/healthz",
        "/status",
    )

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.enabled: bool = getattr(settings, "ONBOARDING_REDIRECT_ENABLED", True)

    def _is_ajax(self, request: HttpRequest) -> bool:
        return request.headers.get("x-requested-with", "").lower() == "xmlhttprequest"

    def _has_exempt_prefix(self, path: str) -> bool:
        return any(path.startswith(p) for p in self.EXEMPT_PREFIXES)

    def _is_exempt_view(self, match: ResolverMatch | None) -> bool:
        return bool(match and match.view_name in self.EXEMPT_VIEW_NAMES)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        # Fast-pass if feature is disabled
        if not self.enabled:
            return self.get_response(request)

        # Only act for authenticated users
        if not request.user.is_authenticated:
            return self.get_response(request)

        # Only intercept safe, top-level page loads (avoid POST/PUT/AJAX)
        if request.method != "GET" or self._is_ajax(request):
            return self.get_response(request)

        # Skip common non-app and system paths early
        if self._has_exempt_prefix(request.path_info):
            return self.get_response(request)

        try:
            match = resolve(request.path_info)
        except Exception:
            # If resolve fails for any reason, do nothing
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
