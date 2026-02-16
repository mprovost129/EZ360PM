from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from companies.services import get_active_company

from .forms_recurring import RecurringPlanForm, RecurringPlanLineItemFormSet
from .models import RecurringPlan
from .services_recurring import generate_invoice_from_plan


@login_required
def recurring_plan_list(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    plans = (
        RecurringPlan.objects.filter(company=company, deleted_at__isnull=True)
        .select_related("client", "project")
        .order_by("-updated_at")
    )
    return render(request, "documents/recurring_plan_list.html", {"plans": plans})


@login_required
def recurring_plan_create(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    if request.method == "POST":
        form = RecurringPlanForm(request.POST, request=request)
        formset = RecurringPlanLineItemFormSet(request.POST)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                plan = form.save(commit=False)
                plan.company = company
                try:
                    plan.created_by = getattr(request.user, "employee_profile", None)
                except Exception:
                    plan.created_by = None
                plan.save()
                formset.instance = plan
                formset.save()
            messages.success(request, "Recurring plan created.")
            return redirect("documents:recurring_plan_list")
    else:
        form = RecurringPlanForm(request=request)
        formset = RecurringPlanLineItemFormSet()

    return render(
        request,
        "documents/recurring_plan_form.html",
        {"form": form, "formset": formset, "mode": "create"},
    )


@login_required
def recurring_plan_edit(request: HttpRequest, pk) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    plan = get_object_or_404(RecurringPlan, pk=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        form = RecurringPlanForm(request.POST, instance=plan, request=request)
        formset = RecurringPlanLineItemFormSet(request.POST, instance=plan)
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                form.save()
                formset.save()
            messages.success(request, "Recurring plan updated.")
            return redirect("documents:recurring_plan_list")
    else:
        form = RecurringPlanForm(instance=plan, request=request)
        formset = RecurringPlanLineItemFormSet(instance=plan)

    return render(
        request,
        "documents/recurring_plan_form.html",
        {"form": form, "formset": formset, "mode": "edit", "plan": plan},
    )


@login_required
def recurring_plan_run_now(request: HttpRequest, pk) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    plan = get_object_or_404(RecurringPlan, pk=pk, company=company, deleted_at__isnull=True)

    if request.method != "POST":
        return redirect("documents:recurring_plan_list")

    result = generate_invoice_from_plan(plan, run_date=timezone.localdate())
    if result.skipped:
        messages.warning(request, f"Did not run plan: {result.message}")
        return redirect("documents:recurring_plan_list")

    messages.success(request, "Invoice created from recurring plan.")
    return redirect("documents:invoice_edit", pk=result.created_invoice.pk)


@login_required
def recurring_plan_toggle(request: HttpRequest, pk) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        return redirect("companies:switch")

    plan = get_object_or_404(RecurringPlan, pk=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        plan.is_active = not plan.is_active
        plan.save(update_fields=["is_active", "updated_at"])
        messages.success(request, "Plan status updated.")
    return redirect("documents:recurring_plan_list")
