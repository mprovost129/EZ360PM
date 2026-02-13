from __future__ import annotations

from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from companies.decorators import require_min_role
from companies.models import EmployeeRole

from audit.services import log_event

from .forms import PaymentForm, PaymentRefundForm
from .models import ClientCreditLedgerEntry, Payment, PaymentStatus, PaymentMethod, PaymentRefund, PaymentRefundStatus
from .services import apply_payment_and_recalc, refund_payment_and_recalc


@require_min_role(EmployeeRole.MANAGER)
def payment_list(request):
    company = request.active_company
    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()

    qs = Payment.objects.filter(company=company).select_related("client", "invoice").order_by("-payment_date", "-created_at")
    if q:
        qs = qs.filter(
            Q(client__company_name__icontains=q)
            | Q(client__first_name__icontains=q)
            | Q(client__last_name__icontains=q)
            | Q(invoice__number__icontains=q)
        )
    if status:
        qs = qs.filter(status=status)

    statuses = [("", "All")] + list(PaymentStatus.choices)

    return render(
        request,
        "payments/payment_list.html",
        {
            "payments": qs[:500],
            "q": q,
            "status": status,
            "statuses": statuses,
        },
    )


@require_min_role(EmployeeRole.MANAGER)
def payment_create(request):
    company = request.active_company
    employee = request.active_employee

    if request.method == "POST":
        form = PaymentForm(request.POST, company=company)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.company = company
            payment.created_by = employee

            # if invoice selected, set client from invoice
            if payment.invoice and payment.invoice.client:
                payment.client = payment.invoice.client

            payment.save()

            # Apply/recalc only if succeeded
            if payment.status == PaymentStatus.SUCCEEDED:
                apply_payment_and_recalc(payment, actor=employee)

            log_event(
                company=company,
                actor=employee,
                event_type="payment.created",
                object_type="Payment",
                object_id=payment.id,
                summary="Payment created",
                payload={"payment_id": str(payment.id)},
                request=request,
            )

            messages.success(request, "Payment saved.")
            return redirect("payments:payment_list")
    else:
        form = PaymentForm(company=company)

    return render(request, "payments/payment_form.html", {"form": form, "mode": "new"})


@require_min_role(EmployeeRole.MANAGER)
def payment_edit(request, pk):
    company = request.active_company
    employee = request.active_employee
    payment = get_object_or_404(Payment, company=company, pk=pk)

    if request.method == "POST":
        form = PaymentForm(request.POST, instance=payment, company=company)
        if form.is_valid():
            payment = form.save(commit=False)
            if payment.invoice and payment.invoice.client:
                payment.client = payment.invoice.client
            payment.save()
            if payment.status == PaymentStatus.SUCCEEDED:
                apply_payment_and_recalc(payment, actor=employee)

            log_event(
                company=company,
                actor=employee,
                event_type="payment.updated",
                object_type="Payment",
                object_id=payment.id,
                summary="Payment updated",
                payload={"payment_id": str(payment.id)},
                request=request,
            )

            messages.success(request, "Payment updated.")
            return redirect("payments:payment_list")
    else:
        form = PaymentForm(instance=payment, company=company)

    refund_form = None
    refundable_cents = max(0, int(payment.amount_cents or 0) - int(getattr(payment, "refunded_cents", 0) or 0))
    if payment.status in [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED] and refundable_cents > 0:
        refund_form = PaymentRefundForm(payment=payment)

    return render(
        request,
        "payments/payment_form.html",
        {
            "form": form,
            "mode": "edit",
            "payment": payment,
            "refund_form": refund_form,
            "refundable_cents": refundable_cents,
        },
    )



@require_min_role(EmployeeRole.MANAGER)
def payment_refund(request, pk):
    company = request.active_company
    employee = request.active_employee
    payment = get_object_or_404(Payment, company=company, pk=pk)

    refundable_cents = max(0, int(payment.amount_cents or 0) - int(getattr(payment, "refunded_cents", 0) or 0))
    if request.method != "POST":
        messages.error(request, "Refund requests must be submitted via POST.")
        return redirect("payments:payment_edit", pk=payment.pk)

    form = PaymentRefundForm(request.POST, payment=payment)
    if not form.is_valid():
        # Re-render edit page with errors
        return render(
            request,
            "payments/payment_form.html",
            {
                "form": PaymentForm(instance=payment, company=company),
                "mode": "edit",
                "payment": payment,
                "refund_form": form,
                "refundable_cents": refundable_cents,
            },
        )

    cents = int(form.cleaned_data["amount_cents"])
    memo = (form.cleaned_data.get("memo") or "").strip()

    refund = PaymentRefund.objects.create(
        company=company,
        payment=payment,
        cents=cents,
        status=PaymentRefundStatus.PENDING,
        memo=memo,
        created_by=employee,
        stripe_charge_id=payment.stripe_charge_id or "",
        stripe_payment_intent_id=payment.stripe_payment_intent_id or "",
    )

    # Best-effort Stripe refund (optional). If Stripe isn't configured, mark failed and require manual processing.
    stripe_ok = False
    try:
        from django.conf import settings
        import stripe

        if getattr(settings, "STRIPE_SECRET_KEY", ""):
            stripe.api_key = settings.STRIPE_SECRET_KEY
            if payment.stripe_payment_intent_id:
                resp = stripe.Refund.create(payment_intent=payment.stripe_payment_intent_id, amount=cents)
                refund.stripe_refund_id = resp.get("id") or ""
                stripe_ok = True
            elif payment.stripe_charge_id:
                resp = stripe.Refund.create(charge=payment.stripe_charge_id, amount=cents)
                refund.stripe_refund_id = resp.get("id") or ""
                stripe_ok = True
    except Exception:
        stripe_ok = False

    if stripe_ok:
        refund.status = PaymentRefundStatus.SUCCEEDED
        refund.processed_at = timezone.now()
        refund.save(update_fields=["status", "stripe_refund_id", "processed_at", "updated_at"])
        refund_payment_and_recalc(refund, actor=employee)

        log_event(
            company=company,
            actor=employee,
            event_type="payment.refunded",
            object_type="PaymentRefund",
            object_id=refund.id,
            summary="Payment refunded",
            payload={"payment_id": str(payment.id), "refund_id": str(refund.id), "cents": cents},
            request=request,
        )
        messages.success(request, "Refund created and applied.")
    else:
        refund.status = PaymentRefundStatus.FAILED
        refund.processed_at = timezone.now()
        refund.save(update_fields=["status", "processed_at", "updated_at"])
        messages.warning(
            request,
            "Refund record created, but Stripe refund could not be executed (missing Stripe config/IDs). "
            "Process the refund in Stripe, then mark it succeeded in admin (v1).",
        )

    return redirect("payments:payment_edit", pk=payment.pk)


@require_min_role(EmployeeRole.MANAGER)
def payment_delete(request, pk):
    company = request.active_company
    employee = request.active_employee
    payment = get_object_or_404(Payment, company=company, pk=pk)

    if request.method == "POST":
        payment.is_deleted = True
        payment.deleted_at = timezone.now()
        payment.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

        log_event(
            company=company,
            actor=employee,
            event_type="payment.deleted",
            object_type="Payment",
            object_id=payment.id,
            summary="Payment deleted",
            payload={"payment_id": str(payment.id)},
            request=request,
        )

        messages.success(request, "Payment deleted.")
        return redirect("payments:payment_list")

    return render(request, "payments/payment_delete.html", {"payment": payment})


@require_min_role(EmployeeRole.MANAGER)
def credit_summary(request):
    company = request.active_company

    entries = (
        ClientCreditLedgerEntry.objects.filter(company=company)
        .select_related("client", "invoice")
        .order_by("-created_at")
    )

    return render(request, "payments/credit_summary.html", {"entries": entries[:500]})
