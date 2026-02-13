from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from audit.services import log_event
from companies.decorators import require_min_role
from companies.models import EmployeeRole

from .forms import ExpenseForm, MerchantForm
from .models import Expense, ExpenseStatus, Merchant


@require_min_role(EmployeeRole.MANAGER)
def merchant_list(request):
    company = request.active_company
    merchants = Merchant.objects.filter(company=company, is_deleted=False).order_by("name")
    return render(request, "expenses/merchant_list.html", {"merchants": merchants})


@require_min_role(EmployeeRole.MANAGER)
def merchant_create(request):
    company = request.active_company
    employee = request.active_employee

    if request.method == "POST":
        form = MerchantForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.company = company
            m.save()
            log_event(company=company, actor=employee, event_type="merchant.created", object_type="Merchant", object_id=m.id, summary="Merchant created", payload={"merchant_id": str(m.id)}, request=request)
            messages.success(request, "Merchant created.")
            return redirect("expenses:merchant_list")
    else:
        form = MerchantForm()

    return render(request, "expenses/merchant_form.html", {"form": form})


@require_min_role(EmployeeRole.MANAGER)
def expense_list(request):
    company = request.active_company
    employee = request.active_employee

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Expense.objects.filter(
        company=company,
        deleted_at=None  # changed from is_deleted=False
    ).select_related("merchant", "client", "project").order_by("-date", "-created_at")
    if q:
        qs = qs.filter(
            Q(description__icontains=q)
            | Q(merchant__name__icontains=q)
            | Q(client__company_name__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
            | Q(project__name__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    statuses = [("", "All")] + list(ExpenseStatus.choices)

    return render(request, "expenses/expense_list.html", {"expenses": qs[:500], "q": q, "status": status, "statuses": statuses})


@require_min_role(EmployeeRole.MANAGER)
def expense_create(request):
    company = request.active_company
    employee = request.active_employee

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, company=company)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.company = company
            exp.created_by = employee
            exp.save()

            log_event(company=company, actor=employee, event_type="expense.created", object_type="Expense", object_id=exp.id, summary="Expense created", payload={"expense_id": str(exp.id)}, request=request)
            messages.success(request, "Expense saved.")
            return redirect("expenses:expense_list")
    else:
        form = ExpenseForm(company=company)

    return render(request, "expenses/expense_form.html", {"form": form, "mode": "new"})


@require_min_role(EmployeeRole.MANAGER)
def expense_edit(request, pk):
    company = request.active_company
    employee = request.active_employee
    exp = get_object_or_404(Expense, company=company, pk=pk)

    if request.method == "POST":
        form = ExpenseForm(request.POST, request.FILES, instance=exp, company=company)
        if form.is_valid():
            exp = form.save(commit=False)
            exp.save()
            log_event(company=company, actor=employee, event_type="expense.updated", object_type="Expense", object_id=exp.id, summary="Expense updated", payload={"expense_id": str(exp.id)}, request=request)
            messages.success(request, "Expense updated.")
            return redirect("expenses:expense_list")
    else:
        form = ExpenseForm(instance=exp, company=company)

    return render(request, "expenses/expense_form.html", {"form": form, "mode": "edit", "expense": exp})


@require_min_role(EmployeeRole.MANAGER)
def expense_delete(request, pk):
    company = request.active_company
    employee = request.active_employee
    exp = get_object_or_404(Expense, company=company, pk=pk)

    if request.method == "POST":
        exp.is_deleted = True
        exp.deleted_at = timezone.now()
        exp.save(update_fields=["is_deleted", "deleted_at", "updated_at"])
        log_event(company=company, actor=employee, event_type="expense.deleted", object_type="Expense", object_id=exp.id, summary="Expense deleted", payload={"expense_id": str(exp.id)}, request=request)
        messages.success(request, "Expense deleted.")
        return redirect("expenses:expense_list")

    return render(request, "expenses/expense_delete.html", {"expense": exp})
