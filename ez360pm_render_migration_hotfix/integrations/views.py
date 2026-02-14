from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from companies.decorators import require_min_role
from companies.models import EmployeeRole
from companies.services import get_active_company

from billing.decorators import tier_required
from billing.models import PlanCode

from .models import DropboxConnection, IntegrationConfig
from .services import (
    dropbox_is_configured,
    build_authorize_url,
    exchange_code_for_token,
    fetch_current_account,
    compute_expires_at,
    new_state,
    new_verifier,
)


@login_required
@tier_required(PlanCode.PREMIUM)
@require_min_role(EmployeeRole.ADMIN)
def dropbox_settings(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    conn = getattr(company, "dropbox_connection", None)
    configured = dropbox_is_configured()

    cfg, _ = IntegrationConfig.objects.get_or_create(company=company)

    if request.method == "POST":
        # Toggle preferences
        cfg.use_dropbox_for_project_files = bool(request.POST.get("use_dropbox_for_project_files"))
        cfg.save(update_fields=["use_dropbox_for_project_files", "updated_at"])
        messages.success(request, "Integration settings saved.")
        return redirect("integrations:dropbox_settings")

    return render(
        request,
        "integrations/dropbox_settings.html",
        {
            "company": company,
            "conn": conn,
            "dropbox_configured": configured,
            "cfg": cfg,
        },
    )


@login_required
@tier_required(PlanCode.PREMIUM)
@require_min_role(EmployeeRole.ADMIN)
def dropbox_connect(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    if not dropbox_is_configured():
        messages.error(request, "Dropbox is not configured yet. Add DROPBOX_APP_KEY and DROPBOX_APP_SECRET.")
        return redirect("integrations:dropbox_settings")

    state = new_state()
    verifier = new_verifier()
    request.session["dropbox_oauth_state"] = state
    request.session["dropbox_oauth_verifier"] = verifier

    url = build_authorize_url(request, state=state, verifier=verifier)
    return redirect(url)


@login_required
@tier_required(PlanCode.PREMIUM)
@require_min_role(EmployeeRole.ADMIN)
def dropbox_callback(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    expected_state = request.session.get("dropbox_oauth_state", "")
    verifier = request.session.get("dropbox_oauth_verifier", "")

    state = request.GET.get("state", "")
    code = request.GET.get("code", "")
    error = request.GET.get("error_description") or request.GET.get("error")

    if error:
        messages.error(request, f"Dropbox connection canceled: {error}")
        return redirect("integrations:dropbox_settings")

    if not state or state != expected_state:
        messages.error(request, "Dropbox callback failed (state mismatch). Please try again.")
        return redirect("integrations:dropbox_settings")

    if not code or not verifier:
        messages.error(request, "Dropbox callback failed (missing code). Please try again.")
        return redirect("integrations:dropbox_settings")

    try:
        token = exchange_code_for_token(request, code=code, verifier=verifier)
        # sanity check token
        acct = fetch_current_account(token.access_token)
    except Exception as e:
        messages.error(request, f"Dropbox connection failed: {e}")
        return redirect("integrations:dropbox_settings")

    conn, _ = DropboxConnection.objects.get_or_create(company=company, defaults={"created_by": request.user})
    conn.created_by = conn.created_by or request.user
    conn.access_token = token.access_token
    conn.account_id = token.account_id or str(acct.get("account_id", ""))
    conn.token_type = token.token_type
    conn.scope = token.scope
    conn.expires_at = compute_expires_at(token.expires_in)
    conn.is_active = True
    conn.save()

    messages.success(request, "Dropbox connected.")
    return redirect("integrations:dropbox_settings")


@login_required
@tier_required(PlanCode.PREMIUM)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def dropbox_disconnect(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    conn = getattr(company, "dropbox_connection", None)
    if not conn:
        messages.info(request, "No Dropbox connection to disconnect.")
        return redirect("integrations:dropbox_settings")

    conn.is_active = False
    conn.access_token = ""
    conn.save(update_fields=["is_active", "access_token", "updated_at"])
    messages.success(request, "Dropbox disconnected.")
    return redirect("integrations:dropbox_settings")
