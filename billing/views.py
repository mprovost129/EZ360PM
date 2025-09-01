# billing/views.py
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

import stripe
from stripe import SignatureVerificationError

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from core.models import Invoice, Payment, Notification
from core.services import recalc_invoice, notify_company
from core.utils import get_active_company
from .models import CompanySubscription, SubscriptionTier, WebhookLog

# Configure Stripe
stripe.api_key = settings.STRIPE_SECRET_KEY


# ---------- Helpers ----------
def _site_url(request: HttpRequest) -> str:
    """Prefer settings.SITE_URL, fall back to request absolute base."""
    base = getattr(settings, "SITE_URL", "").rstrip("/")
    if base:
        return base
    return f"{request.scheme}://{request.get_host()}"

def _dec_from_cents(amount_cents: Optional[int]) -> Decimal:
    if amount_cents is None:
        return Decimal("0.00")
    return (Decimal(amount_cents) / Decimal("100")).quantize(Decimal("0.01"))


# ---------- Customer-facing views ----------
@login_required
def plans(request: HttpRequest) -> HttpResponse:
    tiers = SubscriptionTier.objects.order_by("sort")
    company = get_active_company(request)
    sub = getattr(company, "subscription", None) if company else None
    return render(
        request,
        "billing/plans.html",
        {
            "tiers": tiers,
            "company": company,
            "sub": sub,
            "stripe_pk": getattr(settings, "STRIPE_PUBLIC_KEY", ""),
        },
    )


@login_required
def subscribe(request: HttpRequest, slug: str) -> HttpResponse:
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    tier = get_object_or_404(SubscriptionTier, slug=slug)

    success_url = f"{_site_url(request)}{reverse('billing:plans')}?success=1"
    cancel_url = f"{_site_url(request)}{reverse('billing:plans')}?canceled=1"

    customer_kwargs: dict[str, Any] = {}
    if getattr(company, "subscription", None) and company.subscription.stripe_customer_id:  # type: ignore[attr-defined]
        customer_kwargs["customer"] = company.subscription.stripe_customer_id  # type: ignore[attr-defined]

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": tier.stripe_price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"company_id": str(company.id), "tier_slug": tier.slug},  # type: ignore[arg-type]
        **customer_kwargs,
    )
    return redirect(session.url)  # type: ignore[attr-defined]


@login_required
def portal(request: HttpRequest) -> HttpResponse:
    company = get_active_company(request)
    sub = getattr(company, "subscription", None)
    if not (company and sub and sub.stripe_customer_id):
        messages.info(request, "No customer found yet. Start a subscription first.")
        return redirect("billing:plans")

    portal = stripe.billing_portal.Session.create(
        customer=sub.stripe_customer_id,
        return_url=f"{_site_url(request)}{reverse('billing:plans')}",
    )
    return redirect(portal.url)  # type: ignore[attr-defined]


# ---------- Webhook ----------
@csrf_exempt
def webhook_stripe(request: HttpRequest) -> HttpResponse:
    payload = request.body
    sig = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, SignatureVerificationError):
        return HttpResponse(status=400)

    type_ = event.get("type")
    data = event["data"]["object"]
    event_id = event.get("id") or ""

    # Pre-create log
    log = WebhookLog.objects.create(
        stripe_event_id=event_id,
        type=type_ or "",
        raw=event,
    )

    try:
        info: dict[str, Any] = {"invoice": None, "amount": Decimal("0.00"), "external_id": ""}

        if type_ == "checkout.session.completed":
            mode = (data.get("mode") or "").lower()
            if mode == "subscription":
                _handle_checkout_completed(data)
            elif mode == "payment":
                info = _handle_invoice_payment(data)

        elif type_ == "payment_intent.succeeded":
            info = _handle_invoice_payment(data)

        elif type_ in {"charge.refunded", "charge.refund.updated"}:
            info = _handle_refund_from_charge(data)

        elif type_ == "refund.succeeded":
            info = _handle_refund_from_refund(data)

        elif type_ in {
            "customer.subscription.created",
            "customer.subscription.updated",
            "customer.subscription.deleted",
        }:
            _handle_subscription_event(data)

        # success
        log.processed_ok = True
        log.processed_at = timezone.now()
        log.invoice = info.get("invoice")
        log.amount = info.get("amount")
        log.payment_external_id = info.get("external_id") or ""
        log.save()

    except Exception as e:
        log.processed_ok = False
        log.processed_at = timezone.now()
        log.message = f"{type(e).__name__}: {e}"
        log.save()

    return HttpResponse(status=200)


# ---------- Webhook helpers ----------
def _handle_checkout_completed(session: dict[str, Any]) -> None:
    """
    mode=subscription; creates/updates CompanySubscription and syncs status/period.
    """
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    meta = session.get("metadata") or {}
    company_id = meta.get("company_id")
    tier_slug = meta.get("tier_slug")
    if not (company_id and customer_id and subscription_id):
        return

    from core.models import Company  # local import to avoid cycles

    try:
        company = Company.objects.get(id=company_id)
    except Company.DoesNotExist:
        return

    tier = SubscriptionTier.objects.filter(slug=tier_slug).first()
    sub, _ = CompanySubscription.objects.get_or_create(company=company)
    sub.tier = tier
    sub.stripe_customer_id = customer_id
    sub.stripe_subscription_id = subscription_id

    # Pull subscription to sync dates/status
    s = stripe.Subscription.retrieve(subscription_id)
    sub.status = s.status
    sub.current_period_end = timezone.datetime.fromtimestamp(  # type: ignore[assignment]
        s.current_period_end, tz=timezone.utc # type: ignore
    )
    sub.cancel_at_period_end = bool(getattr(s, "cancel_at_period_end", False))
    sub.save()


def _handle_subscription_event(s: dict[str, Any]) -> None:
    subscription_id = s.get("id")
    status = s.get("status")
    current_period_end = s.get("current_period_end")
    cancel_at_period_end = s.get("cancel_at_period_end")

    try:
        sub = CompanySubscription.objects.get(stripe_subscription_id=subscription_id)
    except CompanySubscription.DoesNotExist:
        return

    sub.status = status # type: ignore
    if current_period_end:
        sub.current_period_end = timezone.datetime.fromtimestamp(  # type: ignore[assignment]
            current_period_end, tz=timezone.utc
        )
    sub.cancel_at_period_end = bool(cancel_at_period_end)
    sub.save()


def _handle_invoice_payment(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Handle:
      - checkout.session.completed (mode=payment)
      - payment_intent.succeeded
    Returns log info: {"invoice": inv or None, "amount": Decimal, "external_id": str}
    """
    meta = obj.get("metadata") or {}
    inv = _find_invoice_from_metadata(meta)
    result = {"invoice": inv, "amount": Decimal("0.00"), "external_id": ""}

    if not inv:
        return result

    external_id = ""
    amount_cents: Optional[int] = None

    if obj.get("object") == "checkout.session":
        external_id = obj.get("payment_intent") or ""
        amount_cents = obj.get("amount_total")
    elif obj.get("object") == "payment_intent":
        external_id = obj.get("id") or ""
        amount_cents = obj.get("amount_received")

    paid = _record_payment(inv, amount_cents, external_id=external_id, method="Stripe")
    result.update({"amount": paid, "external_id": external_id})
    return result


def _find_invoice_from_metadata(meta: dict[str, Any]) -> Invoice | None:
    if not meta:
        return None
    invoice_id = meta.get("invoice_id")
    token = meta.get("invoice_token")
    try:
        if invoice_id:
            return Invoice.objects.select_related("company").get(id=invoice_id)
        if token:
            return Invoice.objects.select_related("company").get(public_token=token)
    except Invoice.DoesNotExist:
        return None
    return None


def _record_payment(
    inv: Invoice,
    amount_cents: Optional[int],
    *,
    external_id: str = "",
    method: str = "Stripe",
) -> Decimal:
    """
    Create a Payment (idempotent if external_id provided), recalc invoice,
    and emit a notification. Returns Decimal amount recorded (positive).
    """
    amount = _dec_from_cents(amount_cents)

    if external_id:
        Payment.objects.get_or_create(
            company=inv.company,
            invoice=inv,
            external_id=external_id,
            defaults={
                "amount": amount,
                "received_at": timezone.now(),
                "method": method,
            },
        )
    else:
        Payment.objects.create(
            company=inv.company,
            invoice=inv,
            amount=amount,
            received_at=timezone.now(),
            method=method,
        )

    recalc_invoice(inv)
    if inv.total and inv.amount_paid >= inv.total and inv.status != Invoice.PAID:
        inv.status = Invoice.PAID
        inv.save(update_fields=["status"])

    try:
        notify_company(
            inv.company,
            actor=None,
            text=f"Payment received for invoice {inv.number} ({amount}).",
            url=reverse("core:invoice_detail", args=[inv.pk]),
            kind=Notification.INVOICE_PAID,
            exclude_actor=False,
        )
    except Exception:
        # Don't break on notification failures
        pass

    return amount


def _handle_refund_from_charge(charge: dict[str, Any]) -> dict[str, Any]:
    """
    Handle refund events where the object is a Charge:
      - charge.refunded
      - charge.refund.updated
    Creates negative Payments for each refund (idempotent via external_id).
    """
    pi = charge.get("payment_intent") or ""
    refunds = (charge.get("refunds") or {}).get("data", [])
    found_inv: Optional[Invoice] = None
    last_amount = Decimal("0.00")
    last_ext_id = ""

    orig_payment = Payment.objects.filter(external_id=pi).select_related("invoice", "company").first()
    if not orig_payment:
        return {"invoice": None, "amount": Decimal("0.00"), "external_id": ""}

    inv = orig_payment.invoice
    found_inv = inv

    for r in refunds:
        refund_id = r.get("id") or ""
        amt_cents = r.get("amount")
        if not refund_id or amt_cents is None:
            continue
        amount = _dec_from_cents(amt_cents)
        ext = f"{pi}:refund:{refund_id}"

        Payment.objects.get_or_create(
            company=inv.company,
            invoice=inv,
            external_id=ext,
            defaults={
                "amount": -amount,
                "received_at": timezone.now(),
                "method": "Stripe Refund",
            },
        )
        last_amount = amount
        last_ext_id = ext

    if found_inv:
        recalc_invoice(found_inv)
        try:
            notify_company(
                found_inv.company,
                actor=None,
                text=f"Refund recorded for invoice {found_inv.number} ({last_amount}).",
                url=reverse("core:invoice_detail", args=[found_inv.pk]),
                kind=Notification.GENERIC,
                exclude_actor=False,
            )
        except Exception:
            pass

    return {"invoice": found_inv, "amount": -last_amount, "external_id": last_ext_id}


def _handle_refund_from_refund(refund: dict[str, Any]) -> dict[str, Any]:
    """
    Handle refund.succeeded events where the object is a Refund.
    """
    refund_id = refund.get("id") or ""
    charge_id = refund.get("charge") or ""
    amount = _dec_from_cents(refund.get("amount"))

    # Need the PaymentIntent ID → fetch charge to read payment_intent
    pi = ""
    try:
        ch = stripe.Charge.retrieve(charge_id) if charge_id else None
        if ch:
            pi = ch.get("payment_intent") or ""
    except Exception:
        pi = ""

    if not pi:
        return {"invoice": None, "amount": Decimal("0.00"), "external_id": ""}

    orig_payment = Payment.objects.filter(external_id=pi).select_related("invoice", "company").first()
    if not orig_payment:
        return {"invoice": None, "amount": Decimal("0.00"), "external_id": ""}

    inv = orig_payment.invoice
    ext = f"{pi}:refund:{refund_id}"

    Payment.objects.get_or_create(
        company=inv.company,
        invoice=inv,
        external_id=ext,
        defaults={
            "amount": -amount,
            "received_at": timezone.now(),
            "method": "Stripe Refund",
        },
    )
    recalc_invoice(inv)
    try:
        notify_company(
            inv.company,
            actor=None,
            text=f"Refund recorded for invoice {inv.number} ({amount}).",
            url=reverse("core:invoice_detail", args=[inv.pk]),
            kind=Notification.GENERIC,
            exclude_actor=False,
        )
    except Exception:
        pass

    return {"invoice": inv, "amount": -amount, "external_id": ext}


# ---------- Admin utility ----------
@staff_member_required
def webhook_logs(request: HttpRequest) -> HttpResponse:
    logs = WebhookLog.objects.order_by("-created_at")[:200]
    return render(request, "billing/webhook_logs.html", {"logs": logs})
