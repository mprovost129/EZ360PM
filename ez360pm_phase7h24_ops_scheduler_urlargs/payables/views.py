from __future__ import annotations

import csv
from datetime import timedelta

from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.conf import settings

from audit.services import log_event
from companies.decorators import require_min_role
from companies.models import EmployeeRole

from core.pagination import paginate
from core.services.private_media import build_private_access_url
from core.s3_presign import presign_private_download, delete_private_object

from .forms import VendorForm, BillForm, BillLineItemForm, BillPaymentForm, RecurringBillPlanForm
from .models import Vendor, Bill, BillStatus, BillLineItem, BillPayment, BillAttachment, RecurringBillPlan
from .services import post_bill_if_needed, post_bill_payment_if_needed
from .services_recurring import generate_bill_from_plan


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
def vendor_detail(request, pk):
    company = request.active_company
    vendor = get_object_or_404(Vendor, pk=pk, company=company)

    bills = (
        Bill.objects.filter(company=company, vendor=vendor)
        .order_by("-issue_date", "-created_at")
    )
    open_bills = bills.filter(status__in=[BillStatus.POSTED, BillStatus.PARTIALLY_PAID])
    total_outstanding_cents = sum(b.balance_cents for b in open_bills)

    recent_payments = (
        BillPayment.objects.filter(bill__company=company, bill__vendor=vendor)
        .select_related("bill")
        .order_by("-payment_date", "-created_at")[:25]
    )

    return render(
        request,
        "payables/vendor_detail.html",
        {
            "vendor": vendor,
            "bills": bills[:50],
            "open_bills": open_bills[:50],
            "total_outstanding_cents": total_outstanding_cents,
            "recent_payments": recent_payments,
        },
    )

@require_min_role(EmployeeRole.MANAGER)
def bill_list(request):
    company = request.active_company
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    due_soon = (request.GET.get("due_soon") or "").strip() in {"1", "true", "yes"}

    qs = Bill.objects.filter(company=company).select_related("vendor").order_by("-issue_date", "-created_at")
    if q:
        qs = qs.filter(Q(vendor__name__icontains=q) | Q(bill_number__icontains=q))
    if status:
        qs = qs.filter(status=status)

    if due_soon:
        today = timezone.localdate()
        soon = today + timedelta(days=7)
        qs = qs.filter(
            status__in=[BillStatus.POSTED, BillStatus.PARTIALLY_PAID],
            balance_cents__gt=0,
            due_date__isnull=False,
            due_date__lte=soon,
        )

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
            "due_soon": due_soon,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
def ap_aging_report(request):
    """A/P Aging report.

    Buckets are based on due_date relative to today.
    Bills without a due_date are treated as "Current".
    """

    company = request.active_company
    today = timezone.localdate()

    open_bills = (
        Bill.objects.filter(
            company=company,
            status__in=[BillStatus.POSTED, BillStatus.PARTIALLY_PAID],
            balance_cents__gt=0,
        )
        .select_related("vendor")
        .order_by("vendor__name", "due_date", "issue_date")
    )

    rows = []
    totals = {"current": 0, "d1_30": 0, "d31_60": 0, "d61_90": 0, "d90p": 0, "total": 0}

    for b in open_bills:
        due = b.due_date
        days_over = 0
        if due:
            days_over = (today - due).days

        bucket = "current"
        if due and days_over > 0:
            if 1 <= days_over <= 30:
                bucket = "d1_30"
            elif 31 <= days_over <= 60:
                bucket = "d31_60"
            elif 61 <= days_over <= 90:
                bucket = "d61_90"
            else:
                bucket = "d90p"

        totals[bucket] += int(b.balance_cents or 0)
        totals["total"] += int(b.balance_cents or 0)

        rows.append(
            {
                "vendor": b.vendor,
                "bill": b,
                "due_date": b.due_date,
                "days_overdue": max(days_over, 0) if due else 0,
                "bucket": bucket,
                "balance_cents": int(b.balance_cents or 0),
            }
        )

    return render(
        request,
        "payables/ap_aging_report.html",
        {
            "rows": rows,
            "totals": totals,
            "today": today,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
def ap_aging_report_csv(request):
    company = request.active_company
    today = timezone.localdate()

    qs = (
        Bill.objects.filter(
            company=company,
            status__in=[BillStatus.POSTED, BillStatus.PARTIALLY_PAID],
            balance_cents__gt=0,
        )
        .select_related("vendor")
        .order_by("vendor__name", "due_date", "issue_date")
    )

    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = f'attachment; filename="ap_aging_{today.isoformat()}.csv"'

    w = csv.writer(resp)
    w.writerow(["Vendor", "Bill #", "Issue Date", "Due Date", "Days Overdue", "Balance (cents)", "Bucket"])

    for b in qs:
        due = b.due_date
        days_over = 0
        if due:
            days_over = (today - due).days
        bucket = "Current"
        if due and days_over > 0:
            if 1 <= days_over <= 30:
                bucket = "1-30"
            elif 31 <= days_over <= 60:
                bucket = "31-60"
            elif 61 <= days_over <= 90:
                bucket = "61-90"
            else:
                bucket = "90+"

        w.writerow([
            b.vendor.name,
            b.bill_number,
            b.issue_date.isoformat() if b.issue_date else "",
            b.due_date.isoformat() if b.due_date else "",
            max(days_over, 0) if due else 0,
            int(b.balance_cents or 0),
            bucket,
        ])

    return resp


@require_min_role(EmployeeRole.MANAGER)
def bill_add_attachment(request, pk):
    company = request.active_company
    employee = request.active_employee
    bill = get_object_or_404(Bill, pk=pk, company=company)

    if request.method != "POST":
        return redirect("payables:bill_detail", pk=bill.pk)

    file_s3_key = (request.POST.get("file_s3_key") or "").strip()
    original_filename = (request.POST.get("original_filename") or "").strip()
    content_type = (request.POST.get("content_type") or "").strip()

    # validate prefix
    loc = (getattr(settings, "S3_PRIVATE_MEDIA_LOCATION", "private-media") or "private-media").strip("/")
    expected_prefix = f"{loc}/bills/{company.id}/{bill.id}/"

    if not file_s3_key or not file_s3_key.startswith(expected_prefix):
        messages.error(request, "Invalid attachment key.")
        return redirect("payables:bill_detail", pk=bill.pk)

    a = BillAttachment(
        bill=bill,
        uploaded_by=employee,
        original_filename=original_filename,
        content_type=content_type,
        file_s3_key=file_s3_key,
    )
    try:
        a.full_clean()
        a.save()
        log_event(
            company=company,
            actor=employee,
            event_type="bill.attachment_added",
            object_type="Bill",
            object_id=bill.id,
            summary="Bill attachment added",
            payload={"bill_id": str(bill.id), "attachment_id": str(a.id), "file_s3_key": file_s3_key},
            request=request,
        )
        messages.success(request, "Attachment added.")
    except Exception as e:
        messages.error(request, f"Could not add attachment: {e}")

    return redirect("payables:bill_detail", pk=bill.pk)


@require_min_role(EmployeeRole.MANAGER)
def bill_delete_attachment(request, pk, attachment_id):
    company = request.active_company
    employee = request.active_employee
    bill = get_object_or_404(Bill, pk=pk, company=company)
    att = get_object_or_404(BillAttachment, pk=attachment_id, bill=bill)

    if request.method == "POST":
        att.soft_delete(save=True)
        log_event(
            company=company,
            actor=employee,
            event_type="bill.attachment_deleted",
            object_type="Bill",
            object_id=bill.id,
            summary="Bill attachment deleted",
            payload={"bill_id": str(bill.id), "attachment_id": str(att.id)},
            request=request,
        )
        messages.success(request, "Attachment removed.")

    return redirect("payables:bill_detail", pk=bill.pk)


@require_min_role(EmployeeRole.MANAGER)


@require_min_role(EmployeeRole.MANAGER)
def bill_attachment_download(request, pk, attachment_id):
    """Open/download a bill attachment (private media).

    Supports optional preview for PDFs/images via ?preview=1.
    """
    company = request.active_company
    bill = get_object_or_404(Bill, pk=pk, company=company)
    att = get_object_or_404(BillAttachment, pk=attachment_id, bill=bill)

    preview = (request.GET.get("preview") or "").strip() in {"1", "true", "yes", "y", "on"}

    url, err = build_private_access_url(
        file_or_key=att.file_s3_key,
        filename=att.original_filename or "attachment",
        content_type=att.content_type or None,
        preview=preview,
    )
    if not url:
        if err == "local_key_not_supported":
            messages.error(request, "Downloads are not available because S3 is not enabled.")
        else:
            messages.error(request, "Could not generate a download link for that attachment.")
        return redirect("payables:bill_detail", pk=bill.pk)

    return redirect(url)


def bill_create(request):
    company = request.active_company
    employee = request.active_employee

    vendor_id = (request.GET.get("vendor") or "").strip() or None
    initial = {}
    if vendor_id:
        try:
            v = Vendor.objects.filter(company=company, pk=vendor_id).first()
            if v:
                initial["vendor"] = v
        except Exception:
            pass

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
        form = BillForm(company=company, initial=initial)

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
            "attachments": bill.attachments.filter(deleted_at__isnull=True).order_by("-created_at"),
            "s3_direct_uploads": bool(getattr(settings, "USE_S3", False) and getattr(settings, "S3_DIRECT_UPLOADS", False)),
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


# -----------------------------------------------------------------------------
# Recurring bills (A/P)
# -----------------------------------------------------------------------------

@require_min_role(EmployeeRole.MANAGER)
def recurring_bill_plan_list(request):
    company = request.active_company
    q = (request.GET.get("q") or "").strip()

    qs = RecurringBillPlan.objects.filter(company=company, deleted_at__isnull=True).select_related("vendor", "expense_account").order_by("next_run", "vendor__name")
    if q:
        qs = qs.filter(Q(vendor__name__icontains=q))

    paged = paginate(request, qs)

    return render(
        request,
        "payables/recurring_bill_plan_list.html",
        {
            "plans": paged.object_list,
            "paginator": paged.paginator,
            "page_obj": paged.page_obj,
            "per_page": paged.per_page,
            "q": q,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
def recurring_bill_plan_create(request):
    company = request.active_company
    employee = request.active_employee

    if request.method == "POST":
        form = RecurringBillPlanForm(request.POST, company=company)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.company = company
            plan.created_by = employee
            plan.updated_by_user = getattr(employee, "user", None)
            plan.save()
            log_event(company=company, actor=employee, event_type="payables.recurring_plan.created", object_type="RecurringBillPlan", object_id=plan.id, summary="Recurring bill plan created", payload={"plan_id": str(plan.id)}, request=request)
            messages.success(request, "Recurring bill plan created.")
            return redirect("payables:recurring_bill_plan_list")
    else:
        form = RecurringBillPlanForm(company=company)

    return render(request, "payables/recurring_bill_plan_form.html", {"form": form, "mode": "new"})


@require_min_role(EmployeeRole.MANAGER)
def recurring_bill_plan_edit(request, pk):
    company = request.active_company
    employee = request.active_employee

    plan = get_object_or_404(RecurringBillPlan, pk=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        form = RecurringBillPlanForm(request.POST, instance=plan, company=company)
        if form.is_valid():
            plan = form.save(commit=False)
            plan.updated_by_user = getattr(employee, "user", None)
            plan.save()
            log_event(company=company, actor=employee, event_type="payables.recurring_plan.updated", object_type="RecurringBillPlan", object_id=plan.id, summary="Recurring bill plan updated", payload={"plan_id": str(plan.id)}, request=request)
            messages.success(request, "Recurring bill plan updated.")
            return redirect("payables:recurring_bill_plan_list")
    else:
        form = RecurringBillPlanForm(instance=plan, company=company)

    return render(request, "payables/recurring_bill_plan_form.html", {"form": form, "mode": "edit", "plan": plan})


@require_min_role(EmployeeRole.MANAGER)
def recurring_bill_plan_delete(request, pk):
    company = request.active_company
    employee = request.active_employee

    plan = get_object_or_404(RecurringBillPlan, pk=pk, company=company, deleted_at__isnull=True)

    if request.method == "POST":
        plan.soft_delete(user=getattr(employee, "user", None))
        log_event(company=company, actor=employee, event_type="payables.recurring_plan.deleted", object_type="RecurringBillPlan", object_id=plan.id, summary="Recurring bill plan deleted", payload={"plan_id": str(plan.id)}, request=request)
        messages.success(request, "Recurring bill plan deleted.")
        return redirect("payables:recurring_bill_plan_list")

    return render(request, "payables/recurring_bill_plan_delete.html", {"plan": plan})


@require_min_role(EmployeeRole.MANAGER)
def recurring_bill_plan_run_now(request, pk):
    company = request.active_company
    employee = request.active_employee

    plan = get_object_or_404(RecurringBillPlan, pk=pk, company=company, deleted_at__isnull=True)

    if request.method != "POST":
        return redirect("payables:recurring_bill_plan_list")

    bill = generate_bill_from_plan(plan=plan, run_date=timezone.localdate(), actor=employee, force=True)
    if bill:
        messages.success(request, "Bill generated.")
        return redirect("payables:bill_detail", pk=bill.id)

    messages.warning(request, "Nothing to run.")
    return redirect("payables:recurring_bill_plan_list")
