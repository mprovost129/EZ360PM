# company/views.py
from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .forms import CompanyForm, InviteForm, MemberForm
from .models import Company, CompanyInvite, CompanyMember
from .utils import (
    get_active_company,
    get_user_companies,
    require_company_admin,
    set_active_company,
)


@login_required
@require_http_methods(["GET"])
def company_profile(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.info(request, "Create your company profile to get started.")
        return redirect("company:company_create")

    # Role of current user in this company (owner, admin, member or None)
    role = (
        CompanyMember.OWNER
        if company.owner_id == request.user.id  # type: ignore[attr-defined]
        else CompanyMember.objects.filter(company=company, user=request.user)
                                 .values_list("role", flat=True)
                                 .first()
    )

    invites = (CompanyInvite.objects
               .filter(company=company, status=CompanyInvite.PENDING)
               .only("id", "email", "role", "sent_at")
               .order_by("-sent_at"))

    members = (CompanyMember.objects
               .filter(company=company)
               .select_related("user")
               .order_by("-joined_at"))

    return render(
        request,
        "company/company_profile.html",
        {
            "company": company,
            "role": role,
            "members": members,
            "invites": invites,
            "companies": get_user_companies(request.user),
        },
    )


@login_required
@require_http_methods(["GET", "POST"])
def company_edit(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    if not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to edit company settings.")
        return redirect("company:company_profile")

    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES, instance=company, owner=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner_id = company.owner_id  # type: ignore # never allow ownership change here
            obj.save()
            messages.success(request, "Company updated.")
            return redirect("company:company_profile")
    else:
        form = CompanyForm(instance=company, owner=request.user)

    return render(request, "company/company_form.html", {"form": form, "company": company})


@login_required
@require_http_methods(["GET"])
def team_list(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    members = (
        CompanyMember.objects.filter(company=company)
        .select_related("user")
        .order_by("-joined_at")
        if company else []
    )
    invites = (
        CompanyInvite.objects.filter(company=company, status=CompanyInvite.PENDING)
        .order_by("-sent_at")
        if company else []
    )
    can_manage = require_company_admin(request.user, company) if company else False
    return render(
        request,
        "core/team_list.html",
        {"company": company, "members": members, "invites": invites, "can_manage": can_manage},
    )


@login_required
@require_http_methods(["GET", "POST"])
def invite_create(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company or not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to invite members.")
        return redirect("company:team_list")

    if request.method == "POST":
        form = InviteForm(request.POST, company=company)
        if form.is_valid():
            inv = form.save(commit=False)
            inv.company = company
            inv.invited_by = request.user
            inv.save()

            invite_path = reverse("core:invite_accept", kwargs={"token": inv.token})
            invite_url = request.build_absolute_uri(invite_path)
            messages.success(request, f"Invite sent to {inv.email}. Link: {invite_url}")
            # (Optionally email this link)
            return redirect("company:team_list")
    else:
        form = InviteForm(company=company)

    return render(request, "core/invite_form.html", {"form": form, "company": company})


@login_required
@require_http_methods(["GET"])
def invite_accept(request: HttpRequest, token) -> HttpResponse:
    inv = get_object_or_404(CompanyInvite, token=token)
    if inv.status != CompanyInvite.PENDING:
        messages.warning(request, "This invite is no longer valid.")
        return redirect("company:company_profile")

    # Require the logged-in user to match the invite email
    if (getattr(request.user, "email", "") or "").lower() != inv.email.lower():
        messages.error(request, "You're signed in with a different email than this invite.")
        return redirect("company:company_profile")

    CompanyMember.objects.get_or_create(
        company=inv.company, user=request.user, defaults={"role": inv.role}
    )
    inv.status = CompanyInvite.ACCEPTED
    inv.accepted_at = timezone.now()
    inv.save(update_fields=["status", "accepted_at"])

    set_active_company(request, inv.company)
    messages.success(request, f"You've joined {inv.company.name} as {inv.role}.")
    return redirect("company:team_list")


@login_required
@require_http_methods(["GET", "POST"])
def member_remove(request: HttpRequest, member_id: int) -> HttpResponse:
    company = get_active_company(request)
    if not company or not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to remove members.")
        return redirect("company:team_list")

    m = get_object_or_404(CompanyMember, pk=member_id, company=company)

    # Prevent removing self
    if m.user_id == request.user.id: # type: ignore
        messages.error(request, "You cannot remove yourself.")
        return redirect("company:team_list")

    # Prevent removing owners (or last owner if you later support multiple owners)
    if m.role == CompanyMember.OWNER:
        messages.error(request, "You cannot remove the company owner.")
        return redirect("company:team_list")

    if request.method == "POST":
        m.delete()
        messages.success(request, "Member removed.")
        return redirect("company:team_list")

    return render(request, "core/member_remove_confirm.html", {"member": m})


@login_required
@require_http_methods(["POST", "GET"])
def company_switch(request: HttpRequest, company_id: int) -> HttpResponse:
    """
    Switch active company — only if the user owns it or is a member.
    """
    c = get_object_or_404(Company, pk=company_id)

    is_owner = (c.owner_id == request.user.id)  # type: ignore[attr-defined]
    is_member = CompanyMember.objects.filter(company=c, user=request.user).exists()

    if not (is_owner or is_member):
        messages.error(request, "You don't have access to that company.")
        return redirect("company:company_profile")

    set_active_company(request, c)
    messages.success(request, f"Switched to {c.name}.")
    return redirect("company:company_profile")


@login_required
@require_http_methods(["GET", "POST"])
def company_create(request: HttpRequest) -> HttpResponse:
    if request.method == "POST":
        form = CompanyForm(request.POST, request.FILES, owner=request.user)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.owner = request.user
            obj.save()
            CompanyMember.objects.get_or_create(
                company=obj, user=request.user, defaults={"role": CompanyMember.OWNER}
            )
            set_active_company(request, obj)
            messages.success(request, "Company created. Welcome!")
            return redirect("company:company_profile")
    else:
        form = CompanyForm(owner=request.user)

    return render(request, "company/company_form.html", {"form": form, "mode": "create"})


@login_required
@require_http_methods(["GET", "POST"])
def member_edit(request: HttpRequest, member_id: int) -> HttpResponse:
    company = get_active_company(request)
    if not company or not require_company_admin(request.user, company):
        messages.error(request, "You don't have permission to edit team members.")
        return redirect("company:team_list")

    m = get_object_or_404(CompanyMember, pk=member_id, company=company)
    if request.method == "POST":
        form = MemberForm(request.POST, instance=m)
        if form.is_valid():
            # Optional: prevent demoting the owner here if you later support editing owners
            if m.role == CompanyMember.OWNER and form.cleaned_data.get("role") != CompanyMember.OWNER:
                messages.error(request, "You cannot change the owner's role.")
                return redirect("company:team_list")
            form.save()
            messages.success(request, "Member updated.")
            return redirect("company:team_list")
    else:
        form = MemberForm(instance=m)

    return render(request, "core/member_form.html", {"form": form, "member": m, "company": company})
