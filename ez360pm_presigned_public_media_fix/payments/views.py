from __future__ import annotations

from django.conf import settings
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

from core.pagination import paginate

from .models import StripeConnectAccount
from .services import (
    stripe_connect_enabled,
    ensure_stripe_connect_account_and_link,
    sync_stripe_connect_account,
)


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

    paged = paginate(request, qs)

    return render(
        request,
        "payments/payment_list.html",
        {
            "payments": paged.object_list,
            "paginator": paged.paginator,
            "page_obj": paged.page_obj,
            "per_page": paged.per_page,
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


@require_min_role(EmployeeRole.MANAGER)
def invoice_reconcile(request, invoice_id):
    company = request.active_company
    employee = request.active_employee

    from documents.models import Document, DocumentType, DocumentStatus
    from documents.models import CreditNote, CreditNoteStatus
    from payments.models import ClientCreditApplication
    from payments.services import recalc_invoice_financials

    invoice = get_object_or_404(Document, company=company, pk=invoice_id, doc_type=DocumentType.INVOICE)

    if request.method == "POST":
        recalc_invoice_financials(invoice, actor=employee)
        messages.success(request, "Recalculated invoice financials.")
        return redirect("payments:invoice_reconcile", invoice_id=str(invoice.id))

    payments = (
        Payment.objects.filter(company=company, invoice=invoice, deleted_at__isnull=True)
        .order_by("-payment_date", "-created_at")
    )
    refunds = (
        PaymentRefund.objects.filter(company=company, payment__invoice=invoice, deleted_at__isnull=True)
        .order_by("-created_at")
        .select_related("payment")
    )
    credit_notes = (
        CreditNote.objects.filter(company=company, invoice=invoice, deleted_at__isnull=True)
        .order_by("-created_at")
    )
    credit_apps = (
        ClientCreditApplication.objects.filter(company=company, invoice=invoice, deleted_at__isnull=True)
        .order_by("-created_at")
    )

    # rollups (in cents)
    payments_gross = sum(int(p.amount_cents or 0) for p in payments if p.status in [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED])
    payments_refunded = sum(int(p.refunded_cents or 0) for p in payments if p.status in [PaymentStatus.SUCCEEDED, PaymentStatus.REFUNDED])
    payments_net = payments_gross - payments_refunded

    refunds_total = sum(int(r.amount_cents or 0) for r in refunds if r.status in [PaymentRefundStatus.SUCCEEDED, PaymentRefundStatus.PENDING])
    credit_note_ar_applied = sum(int(cn.ar_applied_cents or 0) for cn in credit_notes if getattr(cn, "status", None) == CreditNoteStatus.POSTED)
    credit_apps_total = sum(int(a.cents or 0) for a in credit_apps)

    computed_balance = max(0, int(invoice.total_cents or 0) - int(payments_net) - int(credit_note_ar_applied) - int(credit_apps_total))

    return render(
        request,
        "payments/invoice_reconcile.html",
        {
            "invoice": invoice,
            "payments": payments,
            "refunds": refunds,
            "credit_notes": credit_notes,
            "credit_apps": credit_apps,
            "payments_gross": payments_gross,
            "payments_refunded": payments_refunded,
            "payments_net": payments_net,
            "refunds_total": refunds_total,
            "credit_note_ar_applied": credit_note_ar_applied,
            "credit_apps_total": credit_apps_total,
            "computed_balance": computed_balance,
        },
    )


# --------------------------------------------------------------------------------------
# Get Paid (Stripe Connect onboarding)
# --------------------------------------------------------------------------------------


@require_min_role(EmployeeRole.ADMIN)
def get_paid(request):
    """Company payout method setup.

    This is where the company completes Stripe Connect Express onboarding so customer
    invoice payments can be routed to their own Stripe account.
    """

    company = request.active_company

    sca = StripeConnectAccount.objects.filter(company=company).first()
    if sca and stripe_connect_enabled():
        # Best-effort refresh so the UI isn't stale.
        try:
            sca = sync_stripe_connect_account(company)
        except Exception:
            pass

    return render(
        request,
        "payments/get_paid.html",
        {
            "stripe_connect_enabled": stripe_connect_enabled(),
            "sca": sca,
        },
    )


@require_min_role(EmployeeRole.ADMIN)
def get_paid_start(request):
    if request.method != "POST":
        return redirect("payments:get_paid")

    company = request.active_company

    # Build safe absolute URLs (prefer explicit SITE_BASE_URL for canonical host).
    base = (getattr(settings, "SITE_BASE_URL", "") or "").strip().rstrip("/")
    if not base:
        base = request.build_absolute_uri("/").rstrip("/")

    refresh_url = f"{base}/payments/get-paid/"
    return_url = f"{base}/payments/get-paid/return/"

    try:
        _sca, url = ensure_stripe_connect_account_and_link(company, refresh_url=refresh_url, return_url=return_url)
    except Exception as e:
        messages.error(request, f"Could not start Stripe onboarding: {e}")
        return redirect("payments:get_paid")

    if not url:
        messages.error(request, "Stripe did not return an onboarding URL.")
        return redirect("payments:get_paid")

    return redirect(url)


@require_min_role(EmployeeRole.ADMIN)
def get_paid_return(request):
    company = request.active_company
    if stripe_connect_enabled():
        try:
            sca = sync_stripe_connect_account(company)
            if sca.is_ready:
                messages.success(request, "Stripe payout setup is complete. You can now receive invoice payments.")
            else:
                messages.info(request, "Stripe payout setup is not complete yet. Continue onboarding to finish.")
        except Exception:
            # No hard fail; the status can be refreshed from the page.
            messages.info(request, "Returned from Stripe. Refreshing status may take a moment.")
    return redirect("payments:get_paid")
