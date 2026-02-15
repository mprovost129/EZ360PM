from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from audit.services import log_event
from companies.models import Company
from companies.services import set_active_company_id

from .support_mode import clear_support_mode, get_support_mode, set_support_mode


def _staff_required(user) -> bool:
    return bool(user and user.is_authenticated and getattr(user, "is_staff", False))


@login_required
@user_passes_test(_staff_required)
def support_mode_status(request: HttpRequest) -> HttpResponse:
    state = get_support_mode(request)
    company = None
    if state.is_active and state.company_id:
        company = Company.objects.filter(id=state.company_id).first()
    return render(request, "support/mode_status.html", {"state": state, "company": company})


@login_required
@user_passes_test(_staff_required)
def support_mode_enter(request: HttpRequest) -> HttpResponse:
    """Enter time-limited support mode for a target company (audited)."""
    q = (request.GET.get("q") or "").strip()
    companies = []
    if q:
        companies = list(
            Company.objects.filter(deleted_at__isnull=True)
            .filter(Q(name__icontains=q) | Q(id__icontains=q))
            .order_by("name")[:25]
        )

    if request.method == "POST":
        company_id = (request.POST.get("company_id") or "").strip()
        reason = (request.POST.get("reason") or "").strip()
        minutes = int((request.POST.get("minutes") or "30").strip() or 30)

        if not company_id:
            messages.error(request, "Please select a company.")
            return render(request, "support/mode_enter.html", {"q": q, "companies": companies})

        company = Company.objects.filter(deleted_at__isnull=True).filter(id=company_id).first()
        if not company:
            messages.error(request, "Company not found.")
            return render(request, "support/mode_enter.html", {"q": q, "companies": companies})

        state = set_support_mode(request, company_id=str(company.id), minutes=minutes, reason=reason)
        set_active_company_id(request, str(company.id))

        # Audit (actor may be None; include user info in payload)
        log_event(
            company=company,
            actor=None,
            event_type="support.enter",
            object_type="company",
            object_id=company.id,
            summary=f"Support mode entered by staff user {request.user.email}",
            payload={
                "staff_user_id": request.user.id,
                "staff_email": request.user.email,
                "reason": state.reason,
                "minutes": minutes,
                "expires_at": state.expires_at.isoformat() if state.expires_at else None,
            },
            request=request,
        )

        messages.success(request, f"Support mode enabled for {company.name} (expires in {minutes} minutes).")
        return redirect("core:support_mode_status")

    return render(request, "support/mode_enter.html", {"q": q, "companies": companies})


@login_required
@user_passes_test(_staff_required)
@require_POST
def support_mode_exit(request: HttpRequest) -> HttpResponse:
    state = get_support_mode(request)
    company = None
    if state.is_active and state.company_id:
        company = Company.objects.filter(id=state.company_id).first()

    if company:
        log_event(
            company=company,
            actor=None,
            event_type="support.exit",
            object_type="company",
            object_id=company.id,
            summary=f"Support mode exited by staff user {request.user.email}",
            payload={
                "staff_user_id": request.user.id,
                "staff_email": request.user.email,
            },
            request=request,
        )

    clear_support_mode(request)
    messages.success(request, "Support mode disabled.")
    return redirect("core:app_dashboard")
