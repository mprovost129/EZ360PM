from __future__ import annotations

from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.conf import settings
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from audit.services import log_event

from billing.services import build_subscription_summary, can_add_seat
from core.models import SyncModel
from core.pagination import paginate

from .decorators import company_context_required, require_min_role
from .forms import CompanyCreateForm, CompanyInviteForm, CompanySettingsForm
from .models import Company, CompanyInvite, EmployeeProfile, EmployeeRole
from .services import (
    build_login_redirect_with_next,
    clear_active_company_id,
    ensure_unique_username_public,
    generate_invite_token,
    get_active_company,
    get_active_company_id,
    pop_pending_invite,
    remember_pending_invite,
    send_company_invite_email,
    provision_company_defaults,
    set_active_company_id,
    user_companies_qs,
)


def _user_display_name(user) -> str:
    parts = [getattr(user, "first_name", "").strip(), getattr(user, "last_name", "").strip()]
    name = " ".join([p for p in parts if p]).strip()
    return name or getattr(user, "username", "") or getattr(user, "email", "")


@login_required
def onboarding(request: HttpRequest) -> HttpResponse:
    """Create the user's first company if they don't belong to one."""
    if user_companies_qs(request.user).exists():
        return redirect("companies:switch")

    if request.method == "POST":
        form = CompanyCreateForm(request.POST, request.FILES)
        if form.is_valid():
            with transaction.atomic():
                company = form.save()

                # Phase 5B: provision sensible defaults (numbering, templates, chart of accounts)
                provision_company_defaults(company)

                # Security hardening default: require 2FA for managers/admins/owners in production.
                if getattr(settings, "COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS", False):
                    if not getattr(company, "require_2fa_for_admins_managers", False):
                        company.require_2fa_for_admins_managers = True
                        company.save(update_fields=["require_2fa_for_admins_managers", "updated_at", "revision"])
                EmployeeProfile.objects.create(
                    company=company,
                    user=request.user,
                    display_name=_user_display_name(request.user),
                    username_public=request.user.username,
                    role=EmployeeRole.OWNER,
                    can_view_company_financials=True,
                    can_approve_time=True,
                )
                set_active_company_id(request, str(company.id))

                # Ops notification (platform owner): new company signup
                try:
                    from django.db import transaction as _tx
                    from ops.services_notifications import notify_new_company_signup

                    _tx.on_commit(lambda: notify_new_company_signup(company=company))
                except Exception:
                    pass

            messages.success(request, "Company created. Welcome to EZ360PM.")

            # If the user selected a plan from the public pricing page, preselect it
            # and send them straight to Billing to confirm Stripe checkout.
            pre_plan = str(request.session.pop("preselected_plan", "") or "").strip().lower()
            pre_interval = str(request.session.pop("preselected_interval", "") or "").strip().lower()
            plan_map = {"starter": "starter", "professional": "professional", "premium": "premium"}
            interval_map = {"month": "month", "year": "year"}
            if pre_plan in plan_map or pre_interval in interval_map:
                try:
                    from billing.services import ensure_company_subscription
                    from billing.models import PlanCode, BillingInterval

                    sub = ensure_company_subscription(company)
                    changed: list[str] = []
                    if pre_plan in plan_map:
                        desired_plan = plan_map[pre_plan]
                        if desired_plan in {PlanCode.STARTER, PlanCode.PROFESSIONAL, PlanCode.PREMIUM} and desired_plan != sub.plan:
                            sub.plan = desired_plan
                            changed.append("plan")
                    if pre_interval in interval_map:
                        desired_interval = interval_map[pre_interval]
                        if desired_interval in {BillingInterval.MONTH, BillingInterval.YEAR} and desired_interval != sub.billing_interval:
                            sub.billing_interval = desired_interval
                            changed.append("billing_interval")
                    if changed:
                        sub.save(update_fields=changed + ["updated_at"])
                except Exception:
                    pass

                messages.info(request, "Plan selected — confirm your subscription in Billing to start your trial.")
                return redirect("billing:overview")

            return redirect("core:app_dashboard")
    else:
        form = CompanyCreateForm()

    return render(request, "companies/onboarding.html", {"form": form})


@login_required
def switch_company(request: HttpRequest) -> HttpResponse:
    """Company picker page used whenever active company is missing/invalid."""
    companies = list(user_companies_qs(request.user).order_by("name", "created_at"))
    active_id = get_active_company_id(request)

    if request.method == "POST":
        cid = request.POST.get("company_id", "")
        if cid and any(str(c.id) == str(cid) for c in companies):
            set_active_company_id(request, str(cid))
            messages.success(request, "Active company updated.")
            return redirect("core:app_dashboard")
        messages.error(request, "Please select a valid company.")
        return redirect("companies:switch")

    return render(request, "companies/switch.html", {"companies": companies, "active_company_id": active_id})


@login_required
@require_POST
def set_active_company(request: HttpRequest) -> HttpResponse:
    cid = request.POST.get("company_id", "")
    companies = list(user_companies_qs(request.user).values_list("id", flat=True))
    if cid and str(cid) in [str(x) for x in companies]:
        set_active_company_id(request, str(cid))
    return redirect(request.POST.get("next") or "core:app_dashboard")


@login_required
def company_settings(request: HttpRequest) -> HttpResponse:
    """Company settings page.

    Owners/Admins can edit. Others can view only.
    """

    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    employee = (
        EmployeeProfile.objects.filter(company=company, user=request.user, deleted_at__isnull=True)
        .select_related("user")
        .first()
    )
    role = getattr(employee, "role", None)
    can_edit = role in {EmployeeRole.OWNER, EmployeeRole.ADMIN}

    if request.method == "POST":
        form = CompanySettingsForm(request.POST, request.FILES, instance=company)
        if not can_edit:
            for f in form.fields.values():
                f.disabled = True
            messages.warning(request, "You can view settings, but only an Owner or Admin can edit.")
        else:
            if form.is_valid():
                updated = form.save(commit=False)
                updated.updated_by_user = request.user
                updated.save()

                try:
                    log_event(
                        company=company,
                        actor=employee,
                        event_type="company.settings.update",
                        object_type="company",
                        object_id=str(company.id),
                        summary="Updated company settings",
                        request=request,
                    )
                except Exception:
                    pass

                messages.success(request, "Company settings saved.")
                return redirect("companies:settings")
    else:
        form = CompanySettingsForm(instance=company)

    if not can_edit:
        for f in form.fields.values():
            f.disabled = True

    return render(
        request,
        "companies/settings.html",
        {
            "company": company,
            "form": form,
            "can_edit": can_edit,
        },
    )


@company_context_required
def team_list(request: HttpRequest) -> HttpResponse:
    company = request.active_company

    summary = build_subscription_summary(company)
    can_add = can_add_seat(company)

    employees_qs = (
        EmployeeProfile.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("user")
        .order_by("role", "username_public")
    )

    employees_paged = paginate(request, employees_qs)

    invites = (
        CompanyInvite.objects.filter(company=company, deleted_at__isnull=True, accepted_at__isnull=True)
        .order_by("-created_at")
    )

    # Lockout status (account-based). Keyed by user email.
    emails = [e.user.email for e in employees_paged.object_list if getattr(e.user, 'email', None)]
    lockouts = {}
    try:
        from accounts.models import AccountLockout
        rows = AccountLockout.objects.filter(identifier__in=[em.lower() for em in emails])
        for r in rows:
            lockouts[str(r.identifier)] = {
                'is_locked': r.is_locked(),
                'failed_count': int(r.failed_count or 0),
                'locked_until': r.locked_until,
            }
    except Exception:
        lockouts = {}

    return render(
        request,
        "companies/team_list.html",
        {
            "company": company,
            "employees": employees_paged.object_list,
            "paginator": employees_paged.paginator,
            "page_obj": employees_paged.page_obj,
            "per_page": employees_paged.per_page,
            "invites": invites,
            "subscription_summary": summary,
            "can_add_seat": can_add,
            "lockouts": lockouts,
        },
    )


@require_min_role(EmployeeRole.ADMIN)
def invite_create(request: HttpRequest) -> HttpResponse:
    company = request.active_company
    employee = request.active_employee

    if not can_add_seat(company):
        messages.error(request, "Seat limit reached. Upgrade your plan to invite more employees.")
        return redirect("companies:team_list")

    if request.method == "POST":
        form = CompanyInviteForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data["email"].strip().lower()
            username_public = ensure_unique_username_public(company, form.cleaned_data["username_public"])
            role = form.cleaned_data["role"]

            with transaction.atomic():
                existing = (
                    CompanyInvite.objects.filter(
                        company=company, email__iexact=email, accepted_at__isnull=True, deleted_at__isnull=True
                    )
                    .order_by("-created_at")
                    .first()
                )
                if existing:
                    invite = existing
                    invite.username_public = username_public
                    invite.role = role
                    invite.token = generate_invite_token()
                    invite.invited_by = employee
                    invite.expires_at = timezone.now() + timedelta(days=7)
                    invite.updated_by_user = request.user
                    invite.save()
                else:
                    invite = CompanyInvite.objects.create(
                        company=company,
                        email=email,
                        username_public=username_public,
                        role=role,
                        token=generate_invite_token(),
                        invited_by=employee,
                        expires_at=timezone.now() + timedelta(days=7),
                        updated_by_user=request.user,
                    )

            send_company_invite_email(request, invite)
            messages.success(request, f"Invite sent to {invite.email}.")
            return redirect("companies:team_list")
    else:
        form = CompanyInviteForm()

    return render(request, "companies/invite_form.html", {"company": company, "form": form})


@require_min_role(EmployeeRole.ADMIN)
@require_POST
def invite_resend(request: HttpRequest, invite_id) -> HttpResponse:
    company = request.active_company
    invite = get_object_or_404(CompanyInvite, id=invite_id, company=company, deleted_at__isnull=True, accepted_at__isnull=True)
    invite.token = generate_invite_token()
    invite.expires_at = timezone.now() + timedelta(days=7)
    invite.updated_by_user = request.user
    invite.save(update_fields=["token", "expires_at", "updated_by_user", "updated_at", "revision"])
    send_company_invite_email(request, invite)
    messages.success(request, f"Invite resent to {invite.email}.")
    return redirect("companies:team_list")


@require_min_role(EmployeeRole.ADMIN)
@require_POST
def invite_revoke(request: HttpRequest, invite_id) -> HttpResponse:
    company = request.active_company
    invite = get_object_or_404(CompanyInvite, id=invite_id, company=company, deleted_at__isnull=True, accepted_at__isnull=True)
    invite.deleted_at = timezone.now()
    invite.updated_by_user = request.user
    invite.save(update_fields=["deleted_at", "updated_by_user", "updated_at", "revision"])
    messages.success(request, f"Invite revoked for {invite.email}.")
    return redirect("companies:team_list")


def invite_accept(request: HttpRequest, token: str) -> HttpResponse:
    invite = get_object_or_404(CompanyInvite, token=token, deleted_at__isnull=True)

    if invite.accepted_at:
        messages.info(request, "That invitation has already been accepted.")
        return redirect("accounts:login")

    if invite.expires_at and invite.expires_at < timezone.now():
        messages.error(request, "That invitation has expired. Ask your admin to resend it.")
        return redirect("accounts:login")

    # Require login, but keep the token in session so we can resume after auth
    if not request.user.is_authenticated:
        remember_pending_invite(request, token)
        return redirect(build_login_redirect_with_next(request, request.path))

    # Email match guardrail
    user_email = (getattr(request.user, "email", "") or "").strip().lower()
    if user_email and user_email != invite.email.strip().lower():
        messages.error(request, "This invite was sent to a different email address. Please sign in with the invited account.")
        return redirect("core:app_dashboard")

    company = invite.company

    with transaction.atomic():
        # If already an employee, just mark accepted and set active company
        existing = EmployeeProfile.objects.filter(company=company, user=request.user, deleted_at__isnull=True).first()
        if not existing:
            username_public = ensure_unique_username_public(company, invite.username_public)
            EmployeeProfile.objects.create(
                company=company,
                user=request.user,
                display_name=_user_display_name(request.user),
                username_public=username_public,
                role=invite.role,
                can_view_company_financials=(invite.role in (EmployeeRole.ADMIN, EmployeeRole.OWNER)),
                can_approve_time=(invite.role in (EmployeeRole.MANAGER, EmployeeRole.ADMIN, EmployeeRole.OWNER)),
                updated_by_user=request.user,
            )

        invite.accepted_at = timezone.now()
        invite.updated_by_user = request.user
        invite.save(update_fields=["accepted_at", "updated_by_user", "updated_at", "revision"])

    set_active_company_id(request, str(company.id))
    messages.success(request, f"Welcome to {company.name}. You're all set.")
    return redirect("core:app_dashboard")


@require_min_role(EmployeeRole.ADMIN)
@require_POST
def employee_unlock(request: HttpRequest, employee_id: int) -> HttpResponse:
    company = request.active_company
    emp = get_object_or_404(EmployeeProfile, id=employee_id, company=company, deleted_at__isnull=True)

    # Clear account lockout (by email)
    try:
        from accounts.lockouts import clear_for_user_email
        clear_for_user_email(emp.user.email)
    except Exception:
        pass

    # Audit
    log_event(
        company=company,
        actor=request.active_employee,
        event_type="security.unlock",
        object_type="employee",
        object_id=emp.id,
        summary=f"Unlocked account for {emp.user.email}",
        payload={"unlocked_email": emp.user.email, "unlocked_user_id": emp.user.id},
        request=request,
    )

    messages.success(request, f"Unlocked login for {emp.user.email}.")
    return redirect("companies:team_list_list")
