# expenses/views.py
from __future__ import annotations

# --- Stdlib ---
import csv
from decimal import Decimal

# --- Django ---
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_http_methods

# --- Local apps ---
from billing.utils import enforce_limit_or_upsell
from company.services import notify_company
from company.utils import get_active_company
from core.decorators import require_subscription
from core.models import Notification
from core.utils import default_range_last_30, parse_date

from .forms import ExpenseForm
from .models import Expense


# ===== List =====
@login_required
@require_http_methods(["GET"])
def expenses_list(request):
    company = get_active_company(request)

    q = (request.GET.get("q") or "").strip()
    start = parse_date(request.GET.get("start"))
    end = parse_date(request.GET.get("end"))
    if not start or not end:
        start, end = default_range_last_30()

    qs = (
        Expense.objects
        .filter(company=company, date__range=(start, end))
        .select_related("project")
        .order_by("-date", "-id")
    )

    if q:
        qs = qs.filter(
            Q(description__icontains=q)
            | Q(vendor__icontains=q)
            | Q(category__icontains=q)
            | Q(project__name__icontains=q)
            | Q(project__number__icontains=q)
        )

    total = qs.aggregate(s=Sum("amount")).get("s") or Decimal("0")

    # Pagination (50 per page by default)
    page = request.GET.get("page") or 1
    paginator = Paginator(qs, 50)
    page_obj = paginator.get_page(page)

    return render(
        request,
        "expenses/expenses_list.html",
        {
            "expenses": page_obj,   # iterate over page_obj in template
            "page_obj": page_obj,
            "paginator": paginator,
            "q": q,
            "start": start,
            "end": end,
            "total": total,
        },
    )


# ===== Create =====
@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def expense_create(request):
    company = get_active_company(request)

    count = Expense.objects.filter(company=company).count()
    ok, limit = enforce_limit_or_upsell(company, "max_expenses", count)
    if not ok:
        messages.warning(
            request,
            f"You've reached your plan’s limit of {limit} expenses. Upgrade to add more.",
        )
        return redirect("billing:plans")

    if request.method == "POST":
        form = ExpenseForm(request.POST, company=company)
        if form.is_valid():
            obj = form.save(commit=False)
            obj.company = company
            obj.save()

            notify_company(
                company,
                request.user,
                f"Expense ${obj.amount} • {obj.description or obj.vendor or 'Expense'}",
                url=reverse("expenses:expenses") + f"?q={obj.description or ''}",
                kind=Notification.EXPENSE_ADDED,
            )
            messages.success(request, "Expense created.")
            return redirect("expenses:expenses")
    else:
        form = ExpenseForm(
            company=company,
            initial={"date": timezone.localdate()},
        )

    return render(request, "expenses/expense_form.html", {"form": form, "mode": "create"})


# ===== Update =====
@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def expense_update(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Expense, pk=pk, company=company)

    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=obj, company=company)
        if form.is_valid():
            form.save()
            messages.success(request, "Expense updated.")
            return redirect("expenses:expenses")
    else:
        form = ExpenseForm(instance=obj, company=company)

    return render(
        request,
        "expenses/expense_form.html",
        {"form": form, "mode": "edit", "obj": obj},
    )


# ===== Delete =====
@login_required
@require_subscription
@require_http_methods(["GET", "POST"])
def expense_delete(request, pk: int):
    company = get_active_company(request)
    obj = get_object_or_404(Expense, pk=pk, company=company)

    if request.method == "POST":
        obj.delete()
        messages.success(request, "Expense deleted.")
        return redirect("expenses:expenses")

    return render(request, "expenses/expense_confirm_delete.html", {"obj": obj})


@login_required
@require_subscription
@require_http_methods(["GET"])
def expenses_export_csv(request):
    company = get_active_company(request)

    q = (request.GET.get("q") or "").strip()
    start = parse_date(request.GET.get("start"))
    end = parse_date(request.GET.get("end"))
    if not start or not end:
        start, end = default_range_last_30()

    qs = (
        Expense.objects
        .filter(company=company, date__range=(start, end))
        .select_related("project", "invoice")
        .order_by("-date", "-id")
    )
    if q:
        qs = qs.filter(
            Q(description__icontains=q)
            | Q(vendor__icontains=q)
            | Q(category__icontains=q)
            | Q(project__name__icontains=q)
            | Q(project__number__icontains=q)
        )

    # Prepare response
    filename = f"expenses_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    response["Cache-Control"] = "no-store"

    # Write UTF-8 BOM for Excel friendliness
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow([
        "Date",
        "Vendor",
        "Description",
        "Category",
        "Project Number",
        "Project Name",
        "Billable",
        "Markup %",
        "Amount",
        "Invoice #",
    ])

    def fmt_dec(v: Decimal | None) -> str:
        if v is None:
            return "0.00"
        return f"{Decimal(v):.2f}"

    for e in qs.iterator():
        writer.writerow([
            e.date.isoformat(),
            e.vendor or "",
            e.description or "",
            e.category or "",
            getattr(e.project, "number", "") or "",
            getattr(e.project, "name", "") or "",
            "Yes" if e.is_billable else "No",
            fmt_dec(e.billable_markup_pct),
            fmt_dec(e.amount),
            getattr(e.invoice, "number", "") or "",
        ])

    return response