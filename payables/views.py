from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from audit.services import log_event
from companies.decorators import require_min_role
from companies.models import EmployeeRole

from core.pagination import paginate

from .forms import VendorForm, BillForm, BillLineItemForm, BillPaymentForm
from .models import Vendor, Bill, BillStatus, BillLineItem, BillPayment
from .services import post_bill_if_needed, post_bill_payment_if_needed


@require_min_role(EmployeeRole.MANAGER)
def vendor_list(request):
    company = request.active_company
    q = (request.GET.get("q") or "").strip()

    qs = Vendor.objects.filter(company=company).order_by("name")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))

    paged = paginate(request, qs)
    return render(
        request,
        "payables/vendor_list.html",
        {
            "vendors": paged.object_list,
            "paginator": paged.paginator,
            "page_obj": paged.page_obj,
            "per_page": paged.per_page,
            "q": q,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
def vendor_create(request):
    company = request.active_company
    employee = request.active_employee

    if request.method == "POST":
        form = VendorForm(request.POST)
        if form.is_valid():
            v = form.save(commit=False)
            v.company = company
            v.save()
            log_event(company=company, actor=employee, event_type="vendor.created", object_type="Vendor", object_id=v.id, summary="Vendor created", payload={"vendor_id": str(v.id)}, request=request)
            messages.success(request, "Vendor created.")
            return redirect("payables:vendor_list")
    else:
        form = VendorForm()

    return render(request, "payables/vendor_form.html", {"form": form, "mode": "new"})


@require_min_role(EmployeeRole.MANAGER)
def vendor_edit(request, pk):
    company = request.active_company
    employee = request.active_employee

    vendor = get_object_or_404(Vendor, pk=pk, company=company)

    if request.method == "POST":
        form = VendorForm(request.POST, instance=vendor)
        if form.is_valid():
            form.save()
            log_event(company=company, actor=employee, event_type="vendor.updated", object_type="Vendor", object_id=vendor.id, summary="Vendor updated", payload={"vendor_id": str(vendor.id)}, request=request)
            messages.success(request, "Vendor updated.")
            return redirect("payables:vendor_list")
    else:
        form = VendorForm(instance=vendor)

    return render(request, "payables/vendor_form.html", {"form": form, "mode": "edit", "vendor": vendor})


@require_min_role(EmployeeRole.MANAGER)
def bill_list(request):
    company = request.active_company
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Bill.objects.filter(company=company).select_related("vendor").order_by("-issue_date", "-created_at")
    if q:
        qs = qs.filter(Q(vendor__name__icontains=q) | Q(bill_number__icontains=q))
    if status:
        qs = qs.filter(status=status)

    statuses = [("", "All")] + list(BillStatus.choices)

    paged = paginate(request, qs)
    return render(
        request,
        "payables/bill_list.html",
        {
            "bills": paged.object_list,
            "paginator": paged.paginator,
            "page_obj": paged.page_obj,
            "per_page": paged.per_page,
            "q": q,
            "status": status,
            "statuses": statuses,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
def bill_create(request):
    company = request.active_company
    employee = request.active_employee

    if request.method == "POST":
        form = BillForm(request.POST, company=company)
        if form.is_valid():
            bill = form.save(commit=False)
            bill.company = company
            bill.created_by = employee
            bill.save()
            log_event(company=company, actor=employee, event_type="bill.created", object_type="Bill", object_id=bill.id, summary="Bill created", payload={"bill_id": str(bill.id)}, request=request)
            messages.success(request, "Bill created. Add line items, then post.")
            return redirect("payables:bill_detail", pk=bill.pk)
    else:
        form = BillForm(company=company)

    return render(request, "payables/bill_form.html", {"form": form, "mode": "new"})


@require_min_role(EmployeeRole.MANAGER)
def bill_edit(request, pk):
    company = request.active_company
    employee = request.active_employee

    bill = get_object_or_404(Bill, pk=pk, company=company)
    if bill.is_posted:
        messages.error(request, "Posted bills cannot be edited.")
        return redirect("payables:bill_detail", pk=bill.pk)

    if request.method == "POST":
        form = BillForm(request.POST, instance=bill, company=company)
        if form.is_valid():
            form.save()
            log_event(company=company, actor=employee, event_type="bill.updated", object_type="Bill", object_id=bill.id, summary="Bill updated", payload={"bill_id": str(bill.id)}, request=request)
            messages.success(request, "Bill updated.")
            return redirect("payables:bill_detail", pk=bill.pk)
    else:
        form = BillForm(instance=bill, company=company)

    return render(request, "payables/bill_form.html", {"form": form, "mode": "edit", "bill": bill})


@require_min_role(EmployeeRole.MANAGER)
def bill_detail(request, pk):
    company = request.active_company
    bill = get_object_or_404(Bill, pk=pk, company=company)

    # keep numbers fresh
    try:
        bill.recalc_totals()
        bill.save(update_fields=["subtotal_cents", "total_cents", "amount_paid_cents", "balance_cents", "status", "updated_at", "revision"])
    except Exception:
        pass

    line_form = BillLineItemForm(company=company)
    pay_form = BillPaymentForm(company=company)

    return render(
        request,
        "payables/bill_detail.html",
        {
            "bill": bill,
            "line_form": line_form,
            "payment_form": pay_form,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
def bill_add_line(request, pk):
    company = request.active_company
    employee = request.active_employee
    bill = get_object_or_404(Bill, pk=pk, company=company)

    if bill.is_posted:
        messages.error(request, "Cannot add lines to a posted bill.")
        return redirect("payables:bill_detail", pk=bill.pk)

    if request.method != "POST":
        return redirect("payables:bill_detail", pk=bill.pk)

    form = BillLineItemForm(request.POST, company=company)
    if form.is_valid():
        li = form.save(commit=False)
        li.bill = bill
        li.save()
        bill.recalc_totals()
        bill.save(update_fields=["subtotal_cents", "total_cents", "amount_paid_cents", "balance_cents", "updated_at", "revision"])
        log_event(company=company, actor=employee, event_type="bill.line_added", object_type="Bill", object_id=bill.id, summary="Bill line added", payload={"bill_id": str(bill.id), "line_id": str(li.id)}, request=request)
        messages.success(request, "Line added.")
    else:
        messages.error(request, "Please correct the line item fields.")

    return redirect("payables:bill_detail", pk=bill.pk)


@require_min_role(EmployeeRole.MANAGER)
def bill_delete_line(request, pk, line_id):
    company = request.active_company
    employee = request.active_employee
    bill = get_object_or_404(Bill, pk=pk, company=company)
    li = get_object_or_404(BillLineItem, pk=line_id, bill=bill)

    if bill.is_posted:
        messages.error(request, "Cannot delete lines from a posted bill.")
        return redirect("payables:bill_detail", pk=bill.pk)

    if request.method == "POST":
        li.delete()
        bill.recalc_totals()
        bill.save(update_fields=["subtotal_cents", "total_cents", "amount_paid_cents", "balance_cents", "updated_at", "revision"])
        log_event(company=company, actor=employee, event_type="bill.line_deleted", object_type="Bill", object_id=bill.id, summary="Bill line deleted", payload={"bill_id": str(bill.id), "line_id": str(li.id)}, request=request)
        messages.success(request, "Line deleted.")

    return redirect("payables:bill_detail", pk=bill.pk)


@require_min_role(EmployeeRole.MANAGER)
def bill_post(request, pk):
    company = request.active_company
    employee = request.active_employee
    bill = get_object_or_404(Bill, pk=pk, company=company)

    if request.method != "POST":
        return redirect("payables:bill_detail", pk=bill.pk)

    try:
        bill.post(actor=employee)
        post_bill_if_needed(bill)
        log_event(company=company, actor=employee, event_type="bill.posted", object_type="Bill", object_id=bill.id, summary="Bill posted", payload={"bill_id": str(bill.id)}, request=request)
        messages.success(request, "Bill posted.")
    except Exception as e:
        messages.error(request, f"Could not post bill: {e}")

    return redirect("payables:bill_detail", pk=bill.pk)


@require_min_role(EmployeeRole.MANAGER)
def bill_add_payment(request, pk):
    company = request.active_company
    employee = request.active_employee
    bill = get_object_or_404(Bill, pk=pk, company=company)

    if request.method != "POST":
        return redirect("payables:bill_detail", pk=bill.pk)

    if not bill.is_posted:
        messages.error(request, "Post the bill before recording a payment.")
        return redirect("payables:bill_detail", pk=bill.pk)

    form = BillPaymentForm(request.POST, company=company)
    if form.is_valid():
        p = form.save(commit=False)
        p.bill = bill
        p.created_by = employee
        try:
            p.save()
            post_bill_payment_if_needed(p)
            log_event(company=company, actor=employee, event_type="bill.payment_added", object_type="Bill", object_id=bill.id, summary="Bill payment recorded", payload={"bill_id": str(bill.id), "payment_id": str(p.id)}, request=request)
            messages.success(request, "Payment recorded.")
        except Exception as e:
            messages.error(request, str(e))
    else:
        messages.error(request, "Please correct the payment fields.")

    return redirect("payables:bill_detail", pk=bill.pk)
