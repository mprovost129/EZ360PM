from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, JsonResponse
from django.shortcuts import redirect, render

from companies.services import ensure_active_company_for_user, get_active_company

from core.onboarding import build_onboarding_checklist, onboarding_progress


def home(request: HttpRequest):
    """Logged-out marketing page (root path)."""
    if request.user.is_authenticated:
        return redirect("core:app_dashboard")
    return render(request, "core/home.html")


@login_required
def app_dashboard(request: HttpRequest):
    """Logged-in dashboard shell. Requires an active company context."""
    if not ensure_active_company_for_user(request):
        return redirect("companies:switch")

    company = get_active_company(request)
    steps = build_onboarding_checklist(company) if company else []
    progress = onboarding_progress(steps) if company else None

    return render(
        request,
        "core/app_dashboard.html",
        {
            "onboarding_steps": steps,
            "onboarding_progress": progress,
        },
    )


def health(request: HttpRequest) -> JsonResponse:
    """Legacy health endpoint. Prefer /healthz for DB-verified checks."""
    from core.middleware import health_payload

    return JsonResponse(health_payload(), status=200)
