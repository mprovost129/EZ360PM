from __future__ import annotations

from datetime import date, timedelta

from django.db.models import F, Q, Sum
from django.db.models.functions import Coalesce
from django.shortcuts import render
from django.utils import timezone

from core.cache_utils import build_company_request_cache_key, get_or_set
from core.csv_utils import csv_response

from companies.decorators import company_context_required, require_min_role
from companies.models import EmployeeRole

from documents.models import Document, DocumentType, DocumentStatus
from billing.decorators import tier_required
from billing.models import PlanCode

from .forms import DateRangeForm
from .models import Account, AccountType, JournalLine, NormalBalance


def _get_range(request):
    form = DateRangeForm(request.GET or None)
    if form.is_valid():
        start = form.cleaned_data.get("start")
        end = form.cleaned_data.get("end")
    else:
        start = None
        end = None
    return form, start, end


def _lines_qs(company, start: date | None, end: date | None):
    qs = (
        JournalLine.objects.filter(entry__company=company, entry__deleted_at__isnull=True)
        .select_related("entry", "account", "client", "project")
    )
    if start:
        qs = qs.filter(entry__entry_date__gte=start)
    if end:
        qs = qs.filter(entry__entry_date__lte=end)
    return qs


def _account_balance_cents(account: Account, debit_total: int, credit_total: int) -> int:
    d = int(debit_total or 0)
    c = int(credit_total or 0)
    if account.normal_balance == NormalBalance.DEBIT:
        return d - c
    return c - d



def _cached_report_context(request, prefix: str, ttl_seconds: int, builder):
    company = request.active_company
    key = build_company_request_cache_key(prefix, str(company.id), request.get_full_path())
    return get_or_set(key, ttl_seconds, builder).value


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def accounting_home(request):
    return render(request, "accounting/home.html")


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def reports_home(request):
    return render(request, "accounting/reports_home.html")


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def profit_loss(request):
    company = request.active_company
    form, start, end = _get_range(request)

    def _build():
        lines = _lines_qs(company, start, end).filter(account__type__in=[AccountType.INCOME, AccountType.EXPENSE])

        by_account = (
            lines.values("account_id", "account__code", "account__name", "account__type", "account__normal_balance")
            .annotate(
                debits=Coalesce(Sum("debit_cents"), 0),
                credits=Coalesce(Sum("credit_cents"), 0),
            )
            .order_by("account__type", "account__code", "account__name")
        )

        income_rows = []
        expense_rows = []
        total_income = 0
        total_expense = 0

        for r in by_account:
            if r["account__type"] == AccountType.INCOME:
                amt = int(r["credits"] or 0) - int(r["debits"] or 0)
                total_income += amt
                income_rows.append({**r, "amount_cents": amt})
            else:
                amt = int(r["debits"] or 0) - int(r["credits"] or 0)
                total_expense += amt
                expense_rows.append({**r, "amount_cents": amt})

        return {
            "income_rows": income_rows,
            "expense_rows": expense_rows,
            "total_income_cents": total_income,
            "total_expense_cents": total_expense,
            "net_cents": total_income - total_expense,
        }

    data = _cached_report_context(request, "profit_loss", 300, _build)
    if request.GET.get("format") == "csv":
        rows = []
        for r in data["income_rows"]:
            rows.append(["Income", r.get("account__code"), r.get("account__name"), int(r.get("amount_cents") or 0)])
        for r in data["expense_rows"]:
            rows.append(["Expense", r.get("account__code"), r.get("account__name"), int(r.get("amount_cents") or 0)])
        rows.append(["", "", "Net", int(data.get("net_cents") or 0)])
        return csv_response("profit_loss.csv", ["Section", "Code", "Account", "Amount (cents)"], rows)
    ctx = {"form": form, **data}
    return render(request, "accounting/profit_loss.html", ctx)


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def trial_balance(request):
    company = request.active_company
    form, start, end = _get_range(request)

    def _build():
        lines = _lines_qs(company, start, end)

        by_account = (
            lines.values("account_id", "account__code", "account__name", "account__type", "account__normal_balance")
            .annotate(debits=Coalesce(Sum("debit_cents"), 0), credits=Coalesce(Sum("credit_cents"), 0))
            .order_by("account__type", "account__code", "account__name")
        )

        rows = []
        total_debits = 0
        total_credits = 0

        for r in by_account:
            d = int(r["debits"] or 0)
            c = int(r["credits"] or 0)
            total_debits += d
            total_credits += c
            rows.append({**r, "debits": d, "credits": c})

        return {"rows": rows, "total_debits": total_debits, "total_credits": total_credits}

    data = _cached_report_context(request, "trial_balance", 300, _build)
    if request.GET.get("format") == "csv":
        rows = []
        for r in data["rows"]:
            rows.append([r.get("account__code"), r.get("account__name"), int(r.get("debits") or 0), int(r.get("credits") or 0)])
        rows.append(["", "Totals", int(data.get("total_debits") or 0), int(data.get("total_credits") or 0)])
        return csv_response("trial_balance.csv", ["Code", "Account", "Debits (cents)", "Credits (cents)"], rows)
    return render(request, "accounting/trial_balance.html", {"form": form, **data})


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def balance_sheet(request):
    company = request.active_company
    form, start, end = _get_range(request)

    def _build():
        lines = _lines_qs(company, start, end)

        by_account = (
            lines.values("account_id", "account__code", "account__name", "account__type", "account__normal_balance")
            .annotate(debits=Coalesce(Sum("debit_cents"), 0), credits=Coalesce(Sum("credit_cents"), 0))
            .order_by("account__type", "account__code", "account__name")
        )

        assets = []
        liabilities = []
        equity = []

        total_assets = 0
        total_liabilities = 0
        total_equity = 0

        for r in by_account:
            at = r["account__type"]
            if at not in {AccountType.ASSET, AccountType.LIABILITY, AccountType.EQUITY}:
                continue
            account = Account(
                company=company,
                code=r["account__code"],
                name=r["account__name"],
                type=at,
                normal_balance=r["account__normal_balance"],
            )
            bal = _account_balance_cents(account, r["debits"], r["credits"])
            row = {**r, "balance_cents": bal}
            if at == AccountType.ASSET:
                total_assets += bal
                assets.append(row)
            elif at == AccountType.LIABILITY:
                total_liabilities += bal
                liabilities.append(row)
            else:
                total_equity += bal
                equity.append(row)

        return {
            "assets": assets,
            "liabilities": liabilities,
            "equity": equity,
            "total_assets": total_assets,
            "total_liabilities": total_liabilities,
            "total_equity": total_equity,
        }

    data = _cached_report_context(request, "balance_sheet", 300, _build)
    if request.GET.get("format") == "csv":
        rows = []
        for r in data["assets"]:
            rows.append(["Assets", r.get("account__code"), r.get("account__name"), int(r.get("balance_cents") or 0)])
        rows.append(["Assets", "", "Total Assets", int(data.get("total_assets") or 0)])
        for r in data["liabilities"]:
            rows.append(["Liabilities", r.get("account__code"), r.get("account__name"), int(r.get("balance_cents") or 0)])
        rows.append(["Liabilities", "", "Total Liabilities", int(data.get("total_liabilities") or 0)])
        for r in data["equity"]:
            rows.append(["Equity", r.get("account__code"), r.get("account__name"), int(r.get("balance_cents") or 0)])
        rows.append(["Equity", "", "Total Equity", int(data.get("total_equity") or 0)])
        return csv_response("balance_sheet.csv", ["Section", "Code", "Account", "Balance (cents)"], rows)
    return render(request, "accounting/balance_sheet.html", {"form": form, **data})


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def general_ledger(request):
    company = request.active_company
    form, start, end = _get_range(request)

    account_id = request.GET.get("account")
    accounts = Account.objects.filter(company=company, is_active=True, deleted_at__isnull=True).order_by("code", "name")
    selected = None
    lines = []
    running = 0

    if account_id:
        selected = accounts.filter(id=account_id).first()
        if selected:
            qs = _lines_qs(company, start, end).filter(account=selected).order_by("entry__entry_date", "created_at")
            for ln in qs:
                delta = int(ln.debit_cents or 0) - int(ln.credit_cents or 0)
                if selected.normal_balance == NormalBalance.CREDIT:
                    delta = -delta
                running += delta
                lines.append({"line": ln, "running_cents": running})

    return render(
        request,
        "accounting/general_ledger.html",
        {
            "form": form,
            "accounts": accounts,
            "selected": selected,
            "lines": lines,
        },
    )


@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def revenue_by_client(request):
    company = request.active_company
    form, start, end = _get_range(request)

    def _build():
        lines = _lines_qs(company, start, end).filter(account__type=AccountType.INCOME)

        rows = list(
            lines.values("client_id", "client__company_name", "client__last_name", "client__first_name")
            .annotate(
                revenue_cents=Coalesce(Sum("credit_cents"), 0) - Coalesce(Sum("debit_cents"), 0),
            )
            .order_by("-revenue_cents")
        )
        return {"rows": rows}

    data = _cached_report_context(request, "revenue_by_client", 300, _build)
    if request.GET.get("format") == "csv":
        rows = []
        for r in data["rows"]:
            name = r.get("client__company_name") or (f"{r.get('client__last_name') or ''}, {r.get('client__first_name') or ''}".strip(", "))
            rows.append([name, int(r.get("revenue_cents") or 0)])
        return csv_response("revenue_by_client.csv", ["Client", "Revenue (cents)"], rows)
    return render(request, "accounting/revenue_by_client.html", {"form": form, **data})




@tier_required(PlanCode.PREMIUM)  # Advanced reporting enhancements: Premium tier
@require_min_role(EmployeeRole.MANAGER)
def project_profitability(request):
    company = request.active_company
    form, start, end = _get_range(request)

    def _build():
        lines = _lines_qs(company, start, end).filter(account__type__in=[AccountType.INCOME, AccountType.EXPENSE])
        by_project = (
            lines.values("project_id", "project__name")
            .annotate(
                income_cents=Coalesce(Sum("credit_cents"), 0) - Coalesce(Sum("debit_cents"), 0, output_field=None),
                expense_cents=Coalesce(Sum("debit_cents"), 0) - Coalesce(Sum("credit_cents"), 0, output_field=None),
            )
            .order_by("project__name")
        )

        rows = []
        for r in by_project:
            income = int(r.get("income_cents") or 0)
            expense = int(r.get("expense_cents") or 0)
            # Only include projects that have activity
            if income == 0 and expense == 0:
                continue
            rows.append(
                {
                    "project_id": r.get("project_id"),
                    "project_name": r.get("project__name") or "(Unassigned)",
                    "income_cents": income,
                    "expense_cents": expense,
                    "net_cents": income - expense,
                }
            )
        return {"rows": rows}

    data = _cached_report_context(request, "project_profitability", 300, _build)
    if request.GET.get("format") == "csv":
        rows = []
        for r in data["rows"]:
            rows.append([r.get("project_name"), int(r.get("income_cents") or 0), int(r.get("expense_cents") or 0), int(r.get("net_cents") or 0)])
        return csv_response("project_profitability.csv", ["Project", "Income (cents)", "Expenses (cents)", "Net (cents)"], rows)

    return render(request, "accounting/project_profitability.html", {"form": form, **data})

@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def accounts_aging(request):
    company = request.active_company
    form, start, end = _get_range(request)

    # Aging is based on current open invoices; date range filters apply to issue_date
    base = (
        Document.objects.filter(
            company=company,
            doc_type=DocumentType.INVOICE,
            deleted_at__isnull=True,
        )
        .exclude(status=DocumentStatus.VOID)
        .only("id", "issue_date", "due_date", "balance_due_cents", "number", "title", "client_id", "project_id", "status", "total_cents")
    )

    if start:
        base = base.filter(issue_date__gte=start)
    if end:
        base = base.filter(issue_date__lte=end)

    today = timezone.localdate()

    def _build():
        buckets_ids = {
            "current": [],
            "1_30": [],
            "31_60": [],
            "61_90": [],
            "90_plus": [],
        }
        totals = {k: 0 for k in buckets_ids.keys()}

        for inv in base:
            bal = int(getattr(inv, "balance_due_cents", 0) or 0)
            if bal <= 0:
                continue
            due = inv.due_date or inv.issue_date or today
            days = (today - due).days
            if days <= 0:
                key = "current"
            elif days <= 30:
                key = "1_30"
            elif days <= 60:
                key = "31_60"
            elif days <= 90:
                key = "61_90"
            else:
                key = "90_plus"

            buckets_ids[key].append(inv.id)
            totals[key] += bal

        return {"buckets_ids": buckets_ids, "totals": totals}

    data = _cached_report_context(request, "accounts_aging", 300, _build)

    # Resolve invoice objects in one query for template usage
    all_ids = []
    for _k, ids in data["buckets_ids"].items():
        all_ids.extend(ids)

    inv_map = {}
    if all_ids:
        qs = (
            Document.objects.filter(company=company, id__in=all_ids, deleted_at__isnull=True)
            .select_related("client", "project")
        )
        inv_map = {inv.id: inv for inv in qs}

    buckets = {k: [inv_map[i] for i in ids if i in inv_map] for k, ids in data["buckets_ids"].items()}
    totals = data["totals"]

    if request.GET.get("format") == "csv":
        rows = []
        for key, invs in buckets.items():
            for inv in invs:
                client_name = getattr(inv.client, "company_name", "") or getattr(inv.client, "full_name", "")
                rows.append([
                    key,
                    getattr(inv, "number", ""),
                    str(getattr(inv, "issue_date", "")),
                    str(getattr(inv, "due_date", "")),
                    client_name,
                    int(getattr(inv, "balance_due_cents", 0) or 0),
                ])
        return csv_response(
            "accounts_aging.csv",
            ["Bucket", "Invoice", "Issue Date", "Due Date", "Client", "Balance Due (cents)"],
            rows,
        )

    return render(
        request,
        "accounting/accounts_aging.html",
        {
            "form": form,
            "buckets": buckets,
            "totals": totals,
            "bucket_current": buckets["current"],
            "bucket_1_30": buckets["1_30"],
            "bucket_31_60": buckets["31_60"],
            "bucket_61_90": buckets["61_90"],
            "bucket_90_plus": buckets["90_plus"],
            "total_current": totals["current"],
            "total_1_30": totals["1_30"],
            "total_31_60": totals["31_60"],
            "total_61_90": totals["61_90"],
            "total_90_plus": totals["90_plus"],
        },
    )



@tier_required(PlanCode.PROFESSIONAL)
@require_min_role(EmployeeRole.MANAGER)
def reconciliation(request):
    """Read-only reconciliation dashboard (v1)."""
    company = request.active_company
    # Last 90 days default window
    end = timezone.localdate()
    start = end - timedelta(days=90)

    invoices = (
        Document.objects.filter(company=company, doc_type=DocumentType.INVOICE, deleted_at__isnull=True)
        .exclude(status=DocumentStatus.VOID)
        .filter(issue_date__gte=start)
        .select_related("client")
        .order_by("-issue_date", "-created_at")
    )

    from django.db.models import Sum
    from payments.models import Payment, PaymentStatus
    from documents.models import CreditNote, CreditNoteStatus

    # Prefetch aggregates per invoice (naive loop but bounded by 90-day set; acceptable v1)
    rows = []
    for inv in invoices[:200]:
        paid = (
            Payment.objects.filter(invoice=inv, status=PaymentStatus.SUCCEEDED, deleted_at__isnull=True)
            .aggregate(total=Sum("amount_cents"))
            .get("total")
            or 0
        )
        credit_applied = (
            CreditNote.objects.filter(invoice=inv, status=CreditNoteStatus.POSTED, deleted_at__isnull=True)
            .aggregate(total=Sum("ar_applied_cents"))
            .get("total")
            or 0
        )
        stripe_charges = list(
            Payment.objects.filter(invoice=inv, status=PaymentStatus.SUCCEEDED, deleted_at__isnull=True)
            .exclude(stripe_charge_id="")
            .values_list("stripe_charge_id", flat=True)
            .distinct()
        )

        total = int(inv.total_cents or 0)
        paid = int(paid or 0)
        credit_applied = int(credit_applied or 0)
        balance = max(0, total - paid - credit_applied)

        status = "matched"
        # Payment-driven status check
        if stripe_charges and paid == 0:
            status = "stripe_only?"
        if paid > total:
            status = "overpaid"
        if credit_applied > total:
            status = "credit_over"
        if balance == 0 and paid < total and credit_applied > 0:
            status = "credit_applied"
        if balance > 0 and (paid > 0 or credit_applied > 0):
            status = "partial"

        rows.append(
            {
                "invoice": inv,
                "client": inv.client,
                "total": total,
                "paid": paid,
                "credit_applied": credit_applied,
                "balance": balance,
                "stripe_charges": stripe_charges,
                "status": status,
            }
        )

    # Unmatched Stripe payments (succeeded with charge id but no invoice linked)
    unmatched = (
        Payment.objects.filter(company=company, status=PaymentStatus.SUCCEEDED, deleted_at__isnull=True)
        .exclude(stripe_charge_id="")
        .filter(invoice__isnull=True)
        .order_by("-created_at")[:200]
    )

    context = {
        "rows": rows,
        "unmatched": unmatched,
        "start": start,
        "end": end,
    }
    return render(request, "accounting/reconciliation.html", context)
