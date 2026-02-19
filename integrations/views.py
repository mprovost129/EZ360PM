from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.core.paginator import Paginator
from django.views.decorators.http import require_POST
from django.utils import timezone

from datetime import timedelta

from companies.decorators import require_min_role
from companies.models import EmployeeRole
from companies.services import get_active_company, get_active_employee

from billing.decorators import tier_required
from billing.models import PlanCode

from expenses.models import Expense, Merchant

from .models import BankAccount, BankConnection, BankRule, BankTransaction, BankReconciliationPeriod, DropboxConnection, IntegrationConfig
from .forms import BankReconciliationPeriodForm, BankRuleForm
from .bank_rules import apply_rules_for_company
from .services import (
    dropbox_is_configured,
    build_authorize_url,
    exchange_code_for_token,
    fetch_current_account,
    compute_expires_at,
    new_state,
    new_verifier,
    bank_feeds_is_configured,
    bank_feeds_is_enabled,
    plaid_create_link_token,
    plaid_exchange_public_token,
    plaid_fetch_accounts,
    plaid_transactions_sync,
    suggest_existing_expense_for_tx,
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


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
def banking_settings(request: HttpRequest) -> HttpResponse:
    """Bank feeds integration.

    For now, this routes to a friendly "Plaid coming soon" landing page.
    The underlying Plaid service code remains in place, but we avoid
    surfacing partial/broken flows until we finalize Plaid onboarding.
    """

    # Temporary product decision: show a stable landing page.
    return render(request, "integrations/banking_coming_soon.html", {})

    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    configured = bank_feeds_is_configured()
    enabled = bank_feeds_is_enabled()

    conn = getattr(company, "bank_connection", None)

    recent_txs = []
    rules = []
    if conn and conn.is_active:
        recent_txs = (
            BankTransaction.objects.filter(account__connection=conn)
            .select_related("account", "linked_expense", "applied_rule")
            .order_by("-posted_date", "-id")[:50]
        )
        rules = list(company.bank_rules.order_by("priority", "id")[:50])

    return render(
        request,
        "integrations/banking_settings.html",
        {
            "company": company,
            "conn": conn,
            "bank_configured": configured,
            "bank_enabled": enabled,
            "recent_txs": recent_txs,
            "rules": rules,
        },
    )


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
def banking_connect(request: HttpRequest) -> HttpResponse:
    """Start bank connection flow.

    The actual Plaid Link UI is launched client-side from the settings page.
    This endpoint exists for legacy links and simply routes to settings.
    """
    return redirect("integrations:banking_settings")


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_link_token(request: HttpRequest) -> JsonResponse:
    company = get_active_company(request)
    if not company:
        return JsonResponse({"ok": False, "error": "Select a company first."}, status=400)

    if not bank_feeds_is_enabled():
        return JsonResponse({"ok": False, "error": "Bank feeds are disabled (PLAID_ENABLED)."}, status=400)

    if not bank_feeds_is_configured():
        return JsonResponse({"ok": False, "error": "Bank feeds are not configured (PLAID_CLIENT_ID/PLAID_SECRET)."}, status=400)

    try:
        link_token = plaid_create_link_token(company=company, user=request.user)
        return JsonResponse({"ok": True, "link_token": link_token})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_exchange(request: HttpRequest) -> JsonResponse:
    company = get_active_company(request)
    if not company:
        return JsonResponse({"ok": False, "error": "Select a company first."}, status=400)

    public_token = (request.POST.get("public_token") or "").strip()
    if not public_token:
        return JsonResponse({"ok": False, "error": "Missing public_token."}, status=400)

    if not bank_feeds_is_enabled() or not bank_feeds_is_configured():
        return JsonResponse({"ok": False, "error": "Bank feeds not enabled/configured."}, status=400)

    try:
        exchanged = plaid_exchange_public_token(public_token=public_token)
        access_token = exchanged.get("access_token", "")
        item_id = exchanged.get("item_id", "")

        conn, _ = BankConnection.objects.get_or_create(company=company, defaults={"created_by": request.user})
        conn.created_by = conn.created_by or request.user
        conn.provider = "plaid"
        conn.access_token = access_token
        conn.item_id = item_id
        conn.is_active = True
        conn.last_sync_error = ""
        conn.last_sync_status = "connected"
        conn.save()

        # Fetch accounts and store/update
        acct_payload = plaid_fetch_accounts(access_token=access_token)
        accounts = acct_payload.get("accounts") or []
        for a in accounts:
            account_id = str(a.get("account_id", ""))
            if not account_id:
                continue
            name = str(a.get("name") or a.get("official_name") or "")
            mask = str(a.get("mask") or "")
            typ = str(a.get("type") or "")
            subtype = str(a.get("subtype") or "")
            currency = str(((a.get("balances") or {}).get("iso_currency_code")) or "USD")
            BankAccount.objects.update_or_create(
                connection=conn,
                account_id=account_id,
                defaults={
                    "name": name,
                    "mask": mask,
                    "type": typ,
                    "subtype": subtype,
                    "currency": currency,
                    "is_active": True,
                },
            )

        return JsonResponse({"ok": True})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_sync(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("integrations:banking_settings")

    conn = getattr(company, "bank_connection", None)
    if not conn or not conn.is_active or not conn.access_token:
        messages.error(request, "Connect a bank account first.")
        return redirect("integrations:banking_settings")

    try:
        cursor = conn.sync_cursor or None
        added_total = 0
        modified_total = 0
        removed_total = 0

        has_more = True
        next_cursor = cursor
        while has_more:
            payload = plaid_transactions_sync(access_token=conn.access_token, cursor=next_cursor)
            added = payload.get("added") or []
            modified = payload.get("modified") or []
            removed = payload.get("removed") or []
            has_more = bool(payload.get("has_more"))
            next_cursor = str(payload.get("next_cursor") or next_cursor or "")

            # Map account_id -> BankAccount
            acct_map = {a.account_id: a for a in conn.accounts.all()}
            for t in added:
                account_id = str(t.get("account_id") or "")
                bank_acct = acct_map.get(account_id)
                if not bank_acct:
                    continue
                tx_id = str(t.get("transaction_id") or "")
                if not tx_id:
                    continue
                name = str(t.get("name") or t.get("merchant_name") or "")
                date_str = t.get("date")
                posted = None
                if date_str:
                    try:
                        posted = timezone.datetime.fromisoformat(str(date_str)).date()
                    except Exception:
                        posted = None
                amt = t.get("amount")
                try:
                    amt_cents = int(round(float(amt) * 100))
                except Exception:
                    amt_cents = 0
                pending = bool(t.get("pending"))
                cats = t.get("category") or []
                cat = ""
                if isinstance(cats, list):
                    cat = " > ".join([str(x) for x in cats if x])
                else:
                    cat = str(cats)

                BankTransaction.objects.update_or_create(
                    account=bank_acct,
                    transaction_id=tx_id,
                    defaults={
                        "posted_date": posted,
                        "name": name,
                        "amount_cents": amt_cents,
                        "is_pending": pending,
                        "category": cat,
                        "raw": t,
                    },
                )
            added_total += len(added)
            modified_total += len(modified)
            removed_total += len(removed)

        conn.sync_cursor = next_cursor or ""
        conn.last_sync_at = timezone.now()
        conn.last_sync_status = "ok"
        conn.last_sync_error = ""
        conn.save(update_fields=["sync_cursor", "last_sync_at", "last_sync_status", "last_sync_error", "updated_at"])

        # Apply rules to new transactions after each sync.
        try:
            updated = apply_rules_for_company(company)
        except Exception:
            updated = 0
        if updated:
            messages.success(request, f"Bank sync complete. Added {added_total} transactions. Rules applied to {updated} transactions.")
        else:
            messages.success(request, f"Bank sync complete. Added {added_total} transactions.")
    except Exception as e:
        conn.last_sync_at = timezone.now()
        conn.last_sync_status = "error"
        conn.last_sync_error = str(e)
        conn.save(update_fields=["last_sync_at", "last_sync_status", "last_sync_error", "updated_at"])
        messages.error(request, f"Bank sync failed: {e}")

    return redirect("integrations:banking_settings")


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
@require_POST
def banking_tx_create_expense(request: HttpRequest, tx_id: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    tx = get_object_or_404(BankTransaction, pk=tx_id, account__connection__company=company)
    if tx.linked_expense_id:
        messages.info(request, "This transaction already has an expense linked.")
        return redirect("expenses:expense_edit", pk=tx.linked_expense_id)
    if tx.status in {BankTransaction.Status.IGNORED, BankTransaction.Status.TRANSFER}:
        messages.error(request, "This transaction is not eligible for expense creation (ignored/transfer).")
        return redirect("integrations:banking_settings")
    if tx.amount_cents <= 0:
        messages.error(request, "Only debit (positive) transactions can be converted to an expense.")
        return redirect("integrations:banking_settings")
    if tx.suggested_existing_expense_id and tx.suggested_existing_expense_score >= 90:
        messages.warning(
            request,
            "This transaction looks like a duplicate of an existing expense. Use ‘Link suggested’ from the review queue instead of creating a new expense.",
        )
        return redirect("integrations:banking_review_queue")


    employee = get_active_employee(request)
    merchant_name = (tx.suggested_merchant_name or tx.name or "").strip()[:160] or "Bank transaction"
    merchant, _ = Merchant.objects.get_or_create(company=company, name=merchant_name)

    exp = Expense.objects.create(
        company=company,
        created_by=employee,
        merchant=merchant,
        date=tx.posted_date,
        category=(tx.suggested_category or tx.category or "")[:120],
        description=f"Imported from bank feed: {tx.transaction_id}",
        amount_cents=int(tx.amount_cents),
        tax_cents=0,
        total_cents=int(tx.amount_cents),
        status="draft",
    )
    tx.linked_expense = exp
    tx.status = BankTransaction.Status.EXPENSE_CREATED
    tx.save(update_fields=["linked_expense", "status"])
    messages.success(request, f"Expense created from transaction. (Expense #{exp.id})")
    return redirect("expenses:expense_edit", pk=exp.pk)

@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
@require_POST
def banking_tx_link_existing(request: HttpRequest, tx_id: int) -> HttpResponse:
    """Link a bank transaction to the suggested existing expense (duplicate prevention)."""
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    tx = get_object_or_404(BankTransaction, pk=tx_id, account__connection__company=company)

    if tx.linked_expense_id:
        messages.info(request, "This transaction is already linked to an expense.")
        return redirect("expenses:expense_edit", pk=tx.linked_expense_id)

    if not tx.suggested_existing_expense_id:
        messages.error(request, "No suggested expense is available to link.")
        return redirect("integrations:banking_review_queue")

    tx.linked_expense_id = tx.suggested_existing_expense_id
    tx.status = BankTransaction.Status.EXPENSE_CREATED
    tx.reviewed_at = timezone.now()
    tx.reviewed_by = request.user
    tx.save(update_fields=["linked_expense", "status", "reviewed_at", "reviewed_by"])

    messages.success(request, f"Linked to existing expense #{tx.suggested_existing_expense_id}.")
    return redirect("expenses:expense_edit", pk=tx.linked_expense_id)



@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
def banking_rules(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")
    rules = company.bank_rules.order_by("priority", "id")
    return render(request, "integrations/banking_rules_list.html", {"company": company, "rules": rules})


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
def banking_rule_create(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    form = BankRuleForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        obj: BankRule = form.save(commit=False)
        obj.company = company
        obj.save()
        messages.success(request, "Rule created.")
        return redirect("integrations:banking_rules")

    return render(request, "integrations/banking_rule_form.html", {"company": company, "form": form, "mode": "create"})


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
def banking_rule_edit(request: HttpRequest, rule_id: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    rule = get_object_or_404(BankRule, pk=rule_id, company=company)
    form = BankRuleForm(request.POST or None, instance=rule)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Rule saved.")
        return redirect("integrations:banking_rules")

    return render(
        request,
        "integrations/banking_rule_form.html",
        {"company": company, "form": form, "mode": "edit", "rule": rule},
    )


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_rule_delete(request: HttpRequest, rule_id: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")
    rule = get_object_or_404(BankRule, pk=rule_id, company=company)
    rule.delete()
    messages.success(request, "Rule deleted.")
    return redirect("integrations:banking_rules")


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_apply_rules(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")
    updated = apply_rules_for_company(company)
    if updated:
        messages.success(request, f"Rules applied to {updated} transactions.")
    else:
        messages.info(request, "No transactions updated (no rules or no matches).")
    return redirect("integrations:banking_settings")


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_tx_mark(request: HttpRequest, tx_id: int, status: str) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")
    tx = get_object_or_404(BankTransaction, pk=tx_id, account__connection__company=company)
    allowed = {BankTransaction.Status.NEW, BankTransaction.Status.IGNORED, BankTransaction.Status.TRANSFER}
    if status not in allowed:
        messages.error(request, "Invalid status.")
        return redirect("integrations:banking_settings")
    tx.status = status
    tx.save(update_fields=["status"])
    messages.success(request, "Transaction updated.")
    return redirect("integrations:banking_settings")


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
def banking_review_queue(request: HttpRequest) -> HttpResponse:
    """Review queue for imported bank transactions.

    Purpose:
    - Give staff a single place to process NEW transactions
    - Bulk ignore/transfer/create expense
    - Suggest potential duplicates (existing expenses) to avoid double-entry
    """

    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    conn = getattr(company, "bank_connection", None)
    if not conn or not conn.is_active:
        messages.error(request, "Connect a bank account first.")
        return redirect("integrations:banking_settings")

    status = (request.GET.get("status") or BankTransaction.Status.NEW).strip()
    allowed_status = {c for c, _ in BankTransaction.Status.choices}
    if status not in allowed_status:
        status = BankTransaction.Status.NEW

    account_id = (request.GET.get("account") or "").strip()
    qs = BankTransaction.objects.filter(account__connection=conn)
    if status:
        qs = qs.filter(status=status)
    if account_id:
        qs = qs.filter(account__account_id=account_id)

    # Default to newest first.
    qs = qs.select_related("account", "linked_expense", "applied_rule", "suggested_existing_expense").order_by("-posted_date", "-id")

    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    # Opportunistically compute/store suggestions for visible transactions.
    # This keeps the page fast on subsequent loads.
    txs = list(page_obj.object_list)
    for tx in txs:
        if tx.linked_expense_id:
            continue
        if tx.suggested_existing_expense_id and tx.suggested_existing_expense_score:
            continue
        exp, score = suggest_existing_expense_for_tx(company=company, tx=tx)
        if exp and score:
            tx.suggested_existing_expense = exp
            tx.suggested_existing_expense_score = int(score)
            tx.save(update_fields=["suggested_existing_expense", "suggested_existing_expense_score"])

    accounts = list(conn.accounts.filter(is_active=True).order_by("name", "id"))
    return render(
        request,
        "integrations/banking_review_queue.html",
        {
            "company": company,
            "conn": conn,
            "accounts": accounts,
            "page_obj": page_obj,
            "status": status,
            "account_filter": account_id,
            "status_choices": BankTransaction.Status.choices,
        },
    )


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
@require_POST
def banking_review_bulk_action(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    conn = getattr(company, "bank_connection", None)
    if not conn or not conn.is_active:
        messages.error(request, "Connect a bank account first.")
        return redirect("integrations:banking_settings")

    action = (request.POST.get("action") or "").strip()
    tx_ids = request.POST.getlist("tx_ids")
    tx_ids = [int(x) for x in tx_ids if str(x).isdigit()]
    if not tx_ids:
        messages.info(request, "Select at least one transaction.")
        return redirect("integrations:banking_review_queue")

    allowed_actions = {"ignore", "transfer", "create_expense", "link_existing"}
    if action not in allowed_actions:
        messages.error(request, "Invalid action.")
        return redirect("integrations:banking_review_queue")

    txs = list(
        BankTransaction.objects.filter(pk__in=tx_ids, account__connection=conn)
        .select_related("account", "linked_expense", "suggested_existing_expense")
        .order_by("id")
    )
    if not txs:
        messages.info(request, "No matching transactions.")
        return redirect("integrations:banking_review_queue")

    employee = get_active_employee(request)
    reviewed_at = timezone.now()

    updated = 0
    created = 0
    linked = 0
    skipped = 0

    for tx in txs:
        tx.reviewed_at = reviewed_at
        tx.reviewed_by = request.user

        if action == "ignore":
            if tx.status != BankTransaction.Status.IGNORED:
                tx.status = BankTransaction.Status.IGNORED
                tx.save(update_fields=["status", "reviewed_at", "reviewed_by"])
                updated += 1
            else:
                skipped += 1
            continue

        if action == "transfer":
            if tx.status != BankTransaction.Status.TRANSFER:
                tx.status = BankTransaction.Status.TRANSFER
                tx.save(update_fields=["status", "reviewed_at", "reviewed_by"])
                updated += 1
            else:
                skipped += 1
            continue

        if action == "link_existing":
            if tx.linked_expense_id:
                skipped += 1
                continue
            if not tx.suggested_existing_expense_id:
                skipped += 1
                continue
            tx.linked_expense_id = tx.suggested_existing_expense_id
            tx.status = BankTransaction.Status.EXPENSE_CREATED
            tx.save(update_fields=["linked_expense", "status", "reviewed_at", "reviewed_by"])
            linked += 1
            continue

        # create_expense
        if tx.linked_expense_id:
            skipped += 1
            continue
        if tx.status in {BankTransaction.Status.IGNORED, BankTransaction.Status.TRANSFER}:
            skipped += 1
            continue
        if tx.amount_cents <= 0:
            skipped += 1
            continue

        # If we have a strong duplicate suggestion, do not create automatically.
        if tx.suggested_existing_expense_id and tx.suggested_existing_expense_score >= 90:
            skipped += 1
            continue

        merchant_name = (tx.suggested_merchant_name or tx.name or "").strip()[:160] or "Bank transaction"
        merchant, _ = Merchant.objects.get_or_create(company=company, name=merchant_name)

        exp = Expense.objects.create(
            company=company,
            created_by=employee,
            merchant=merchant,
            date=tx.posted_date,
            category=(tx.suggested_category or tx.category or "")[:120],
            description=f"Imported from bank feed: {tx.transaction_id}",
            amount_cents=int(tx.amount_cents),
            tax_cents=0,
            total_cents=int(tx.amount_cents),
            status="draft",
        )
        tx.linked_expense = exp
        tx.status = BankTransaction.Status.EXPENSE_CREATED
        tx.save(update_fields=["linked_expense", "status", "reviewed_at", "reviewed_by"])
        created += 1

    if action in {"ignore", "transfer"}:
        messages.success(request, f"Updated {updated} transactions. Skipped {skipped}.")
    elif action == "link_existing":
        messages.success(request, f"Linked {linked} transactions to existing expenses. Skipped {skipped}.")
    else:
        messages.success(request, f"Created {created} draft expenses. Skipped {skipped} (ineligible or possible duplicates).")

    return redirect("integrations:banking_review_queue")


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
def banking_reconcile(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    conn = getattr(company, "bank_connection", None)
    if not conn or not conn.is_active:
        messages.error(request, "Connect a bank account first.")
        return redirect("integrations:banking_settings")

    days = request.GET.get("days") or "30"
    try:
        days_i = max(7, min(180, int(days)))
    except Exception:
        days_i = 30

    start_date = timezone.now().date() - timedelta(days=days_i)

    txs = BankTransaction.objects.filter(account__connection=conn, posted_date__gte=start_date)

    # Summary counts
    total = txs.count()
    by_status = {k: txs.filter(status=k).count() for k, _ in BankTransaction.Status.choices}

    # Per-account totals
    account_rows = []
    for acct in conn.accounts.filter(is_active=True).order_by("name", "id"):
        aqs = txs.filter(account=acct)
        account_rows.append(
            {
                "account": acct,
                "total": aqs.count(),
                "new": aqs.filter(status=BankTransaction.Status.NEW).count(),
                "ignored": aqs.filter(status=BankTransaction.Status.IGNORED).count(),
                "transfer": aqs.filter(status=BankTransaction.Status.TRANSFER).count(),
                "expense_created": aqs.filter(status=BankTransaction.Status.EXPENSE_CREATED).count(),
            }
        )

    return render(
        request,
        "integrations/banking_reconcile.html",
        {
            "company": company,
            "conn": conn,
            "days": days_i,
            "start_date": start_date,
            "total": total,
            "by_status": by_status,
            "account_rows": account_rows,
        },
    )


# ------------------------------------------------------------------------------
# Phase 9 — Bank reconciliation periods (lockable)
# ------------------------------------------------------------------------------


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
def banking_reconciliation_periods(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    qs = BankReconciliationPeriod.objects.filter(company=company).order_by("-start_date", "-id")
    status = (request.GET.get("status") or "").strip()
    if status in {BankReconciliationPeriod.Status.OPEN, BankReconciliationPeriod.Status.LOCKED}:
        qs = qs.filter(status=status)

    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "integrations/banking_reconciliation_periods.html",
        {"company": company, "page_obj": page_obj, "status": status},
    )


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
def banking_reconciliation_new(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    if request.method == "POST":
        form = BankReconciliationPeriodForm(request.POST)
        if form.is_valid():
            period: BankReconciliationPeriod = form.save(commit=False)
            period.company = company
            period.created_by = request.user
            period.save()
            messages.success(request, "Reconciliation period created.")
            return redirect("integrations:banking_reconciliation_detail", pk=period.pk)
    else:
        # Default to the current month-to-date window
        today = timezone.now().date()
        start = today.replace(day=1)
        end = today
        form = BankReconciliationPeriodForm(initial={"start_date": start, "end_date": end})

    return render(
        request,
        "integrations/banking_reconciliation_new.html",
        {"company": company, "form": form},
    )


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
def banking_reconciliation_detail(request: HttpRequest, pk: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    period = get_object_or_404(BankReconciliationPeriod, pk=pk, company=company)

    txs = (
        BankTransaction.objects.filter(
            account__connection__company=company,
            posted_date__gte=period.start_date,
            posted_date__lte=period.end_date,
        )
        .select_related("account", "linked_expense")
        .order_by("-posted_date", "-id")
    )

    eligible_txs = txs.exclude(status__in=[BankTransaction.Status.IGNORED, BankTransaction.Status.TRANSFER]).filter(is_pending=False)

    bank_outflow_cents = sum(int(t.amount_cents) for t in eligible_txs if int(t.amount_cents) > 0)

    matched_txs = eligible_txs.filter(linked_expense__isnull=False)
    unmatched_bank = eligible_txs.filter(linked_expense__isnull=True)

    expenses = Expense.objects.filter(company=company, date__gte=period.start_date, date__lte=period.end_date).order_by("-date", "-id")
    expense_total_cents = sum(int(e.total_cents) for e in expenses)

    matched_expense_ids = set(matched_txs.values_list("linked_expense_id", flat=True))
    unmatched_expenses = expenses.exclude(id__in=matched_expense_ids)

    diff_cents = int(bank_outflow_cents) - int(expense_total_cents)

    bank_page = Paginator(unmatched_bank, 25).get_page(request.GET.get("bp"))
    exp_page = Paginator(unmatched_expenses, 25).get_page(request.GET.get("ep"))

    return render(
        request,
        "integrations/banking_reconciliation_detail.html",
        {
            "company": company,
            "period": period,
            "txs_total": txs.count(),
            "eligible_total": eligible_txs.count(),
            "bank_outflow_cents": bank_outflow_cents,
            "expense_total_cents": expense_total_cents,
            "diff_cents": diff_cents,
            "matched_count": matched_txs.count(),
            "unmatched_bank_count": unmatched_bank.count(),
            "unmatched_expense_count": unmatched_expenses.count(),
            "bank_page": bank_page,
            "exp_page": exp_page,
        },
    )


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_reconciliation_lock(request: HttpRequest, pk: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    period = get_object_or_404(BankReconciliationPeriod, pk=pk, company=company)
    if period.status == BankReconciliationPeriod.Status.LOCKED:
        messages.info(request, "This period is already locked.")
        return redirect("integrations:banking_reconciliation_detail", pk=period.pk)

    txs = (
        BankTransaction.objects.filter(
            account__connection__company=company,
            posted_date__gte=period.start_date,
            posted_date__lte=period.end_date,
        )
        .exclude(status__in=[BankTransaction.Status.IGNORED, BankTransaction.Status.TRANSFER])
        .filter(is_pending=False)
    )

    bank_outflow_cents = sum(int(t.amount_cents) for t in txs if int(t.amount_cents) > 0)
    matched_txs = txs.filter(linked_expense__isnull=False)
    unmatched_bank = txs.filter(linked_expense__isnull=True)

    expenses = Expense.objects.filter(company=company, date__gte=period.start_date, date__lte=period.end_date)
    expense_total_cents = sum(int(e.total_cents) for e in expenses)
    matched_expense_ids = set(matched_txs.values_list("linked_expense_id", flat=True))
    unmatched_expenses = expenses.exclude(id__in=matched_expense_ids)

    period.snapshot_bank_outflow_cents = int(bank_outflow_cents)
    period.snapshot_expense_total_cents = int(expense_total_cents)
    period.snapshot_matched_count = matched_txs.count()
    period.snapshot_unmatched_bank_count = unmatched_bank.count()
    period.snapshot_unmatched_expense_count = unmatched_expenses.count()
    period.save(
        update_fields=[
            "snapshot_bank_outflow_cents",
            "snapshot_expense_total_cents",
            "snapshot_matched_count",
            "snapshot_unmatched_bank_count",
            "snapshot_unmatched_expense_count",
            "updated_at",
        ]
    )

    period.lock(by_user=request.user)
    messages.success(request, "Reconciliation period locked. Snapshot saved.")
    return redirect("integrations:banking_reconciliation_detail", pk=period.pk)


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_reconciliation_unlock(request: HttpRequest, pk: int) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    period = get_object_or_404(BankReconciliationPeriod, pk=pk, company=company)
    if period.status != BankReconciliationPeriod.Status.LOCKED:
        messages.info(request, "This period is already open.")
        return redirect("integrations:banking_reconciliation_detail", pk=period.pk)

    period.unlock()
    messages.warning(request, "Reconciliation period unlocked (undo). Snapshot retained for transparency.")
    return redirect("integrations:banking_reconciliation_detail", pk=period.pk)


@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.STAFF)
def banking_reconciliation_export_csv(request: HttpRequest, pk: int) -> HttpResponse:
    import csv

    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    period = get_object_or_404(BankReconciliationPeriod, pk=pk, company=company)

    txs = (
        BankTransaction.objects.filter(
            account__connection__company=company,
            posted_date__gte=period.start_date,
            posted_date__lte=period.end_date,
        )
        .select_related("account", "linked_expense")
        .order_by("posted_date", "id")
    )

    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = f"attachment; filename=reconciliation_{period.start_date}_{period.end_date}.csv"

    w = csv.writer(response)
    w.writerow(["posted_date", "account", "name", "amount_cents", "status", "linked_expense_id"])
    for t in txs:
        acct_label = t.account.name or (t.account.mask and f"••••{t.account.mask}") or t.account.account_id
        w.writerow([t.posted_date, acct_label, t.name, t.amount_cents, t.status, t.linked_expense_id or ""])

    return response

@login_required
@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.ADMIN)
@require_POST
def banking_disconnect(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "Select a company first.")
        return redirect("core:app_dashboard")

    conn = getattr(company, "bank_connection", None)
    if not conn:
        messages.info(request, "No bank connection to disconnect.")
        return redirect("integrations:banking_settings")

    conn.is_active = False
    conn.access_token = ""
    conn.item_id = ""
    conn.sync_cursor = ""
    conn.last_sync_error = ""
    conn.save(update_fields=["is_active", "access_token", "item_id", "last_sync_error", "updated_at"])
    messages.success(request, "Bank connection removed.")
    return redirect("integrations:banking_settings")
