# onboarding/views.py
from __future__ import annotations

from typing import Optional
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.conf import settings

from core.forms import CompanyForm, ClientForm, ProjectForm
from core.models import CompanyMember, Client, Project
from core.utils import get_active_company, set_active_company, get_user_profile
# from core.decorators import require_subscription  # keep handy if you gate later


def _safe_next(request: HttpRequest, default: str) -> str:
    """Return a safe 'next' destination if provided, else the default."""
    nxt = request.GET.get("next") or request.POST.get("next")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return nxt
    return default


@login_required
def start(request: HttpRequest) -> HttpResponse:
    """
    Decide where to send the user when they enter the wizard.
    If they already have an active company, skip straight to next step.
    """
    company = get_active_company(request)
    dest = "onboarding:client" if company else "onboarding:company"
    return redirect(dest)


@login_required
def company(request: HttpRequest) -> HttpResponse:
    """
    Create the first company (required). If a company already exists/active, skip to next step.
    """
    if get_active_company(request):
        return redirect("onboarding:client")

    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                company = form.save(commit=False)
                # Server-side ownership assignment (ignore any tampering)
                company.owner = request.user
                company.save()

                CompanyMember.objects.get_or_create(
                    company=company,
                    user=request.user,
                    defaults={"role": CompanyMember.OWNER},
                )

                set_active_company(request, company)

            messages.success(request, "Company created.")
            return redirect("onboarding:client")
    else:
        default_name = (getattr(request.user, "name", "") or request.user.email).strip() # type: ignore
        form = CompanyForm(initial={"name": f"{default_name} — Company"})

    return render(request, "onboarding/company.html", {"form": form})


@login_required
def client(request: HttpRequest) -> HttpResponse:
    """
    Optional: add first client. Skippable.
    """
    company = get_active_company(request)
    if not company:
        return redirect("onboarding:company")

    if request.method == "POST":
        if "skip" in request.POST:
            messages.info(request, "Skipped adding a client for now.")
            return redirect("onboarding:project")

        form = ClientForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                obj: Client = form.save(commit=False)
                # Lock company server-side
                obj.company = company
                obj.save()
            messages.success(request, "Client added.")
            return redirect("onboarding:project")
    else:
        form = ClientForm()

    return render(request, "onboarding/client.html", {"form": form})


@login_required
def project(request: HttpRequest) -> HttpResponse:
    """
    Optional: add first project. Skippable.
    """
    company = get_active_company(request)
    if not company:
        return redirect("onboarding:company")

    if request.method == "POST":
        if "skip" in request.POST:
            messages.info(request, "Skipped creating a project for now.")
            return redirect("onboarding:finish")

        form = ProjectForm(request.POST)
        if form.is_valid():
            with transaction.atomic():
                obj: Project = form.save(commit=False)
                # Lock company server-side
                obj.company = company
                obj.save()
                form.save_m2m()
            messages.success(request, "Project created.")
            return redirect("onboarding:finish")
    else:
        form = ProjectForm()

    return render(request, "onboarding/project.html", {"form": form})


@login_required
def finish(request: HttpRequest) -> HttpResponse:
    """
    Mark onboarding complete and go to dashboard.
    """
    profile = get_user_profile(request.user)
    try:
        if hasattr(profile, "onboarded") and not getattr(profile, "onboarded"):
            profile.onboarded = True  # type: ignore[attr-defined]
            profile.save(update_fields=["onboarded"])
    except Exception:
        # Non-fatal; continue
        pass

    messages.success(request, "All set! Welcome to your dashboard.")
    return redirect(_safe_next(request, default="dashboard:home"))


@login_required
def payments(request):
    """
    Optional: connect payments (Stripe) or pick a plan.
    We don't save anything here; it's a guided step to your billing/portal pages.
    """
    company = get_active_company(request)
    if not company:
        return redirect("onboarding:company")

    if request.method == "POST":
        if "skip" in request.POST:
            messages.info(request, "Skipped connecting payments for now.")
            return redirect("onboarding:team")
        # If you add a “Continue” button, just push to team step
        return redirect("onboarding:team")

    # Render simple page with CTAs to plans/portal; company is passed to show portal link when available
    return render(request, "onboarding/payments.html", {"company": company})


@login_required
def team(request):
    """
    Optional: invite teammates.
    This step points users to the team page; no data is captured here.
    """
    company = get_active_company(request)
    if not company:
        return redirect("onboarding:company")

    if request.method == "POST":
        if "skip" in request.POST:
            messages.info(request, "Skipped inviting teammates for now.")
            return redirect("onboarding:finish")
        return redirect("onboarding:finish")

    return render(request, "onboarding/team.html", {"company": company})