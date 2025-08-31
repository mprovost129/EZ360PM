# billing/views.py
import stripe
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from decimal import Decimal

from core.utils import get_active_company
from .models import SubscriptionTier, CompanySubscription, WebhookLog
from django.views.decorators.csrf import csrf_exempt
from stripe import SignatureVerificationError

from core.models import Invoice, Payment, Notification  # add Payment/Notification here
from core.services import recalc_invoice, notify_company


stripe.api_key = settings.STRIPE_SECRET_KEY

@login_required
def plans(request):
    tiers = SubscriptionTier.objects.order_by("sort")
    company = get_active_company(request)
    sub = getattr(company, "subscription", None) if company else None
    return render(request, "billing/plans.html", {"tiers": tiers, "company": company, "sub": sub, "stripe_pk": settings.STRIPE_PUBLIC_KEY})

@login_required
def subscribe(request, slug: str):
    company = get_active_company(request)
    if not company:
        messages.error(request, "No active company.")
        return redirect("dashboard:home")

    tier = get_object_or_404(SubscriptionTier, slug=slug)

    success_url = f"{settings.SITE_URL}{reverse('billing:plans')}?success=1"
    cancel_url = f"{settings.SITE_URL}{reverse('billing:plans')}?canceled=1"

    # Ensure we have or will get a customer record
    customer_kwargs = {}
    if hasattr(company, "subscription") and company.subscription.stripe_customer_id: # type: ignore
        customer_kwargs["customer"] = company.subscription.stripe_customer_id # type: ignore

    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[{"price": tier.stripe_price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        **customer_kwargs,
        metadata={
            "company_id": str(company.id), # type: ignore
            "tier_slug": tier.slug,
        },
    )
    return redirect(session.url)

@login_required
def portal(request):
    company = get_active_company(request)
    if not company or not getattr(company, "subscription", None) or not company.subscription.stripe_customer_id: # type: ignore
        messages.info(request, "No customer found yet. Start a subscription first.")
        return redirect("billing:plans")

    portal = stripe.billing_portal.Session.create(
        customer=company.subscription.stripe_customer_id, # type: ignore
        return_url=f"{settings.SITE_URL}{reverse('billing:plans')}",
    )
    return redirect(portal.url)

# --- Webhook ---

def _handle_invoice_payment(session_or_intent: dict) -> dict:
    """
    Handle payment from checkout.session.completed (mode=payment) or payment_intent.succeeded.
    Returns a dict for logging: {"invoice": inv or None, "amount": Decimal, "external_id": str}
    """
    meta = session_or_intent.get("metadata") or {}
    inv = _find_invoice_from_metadata(meta)
    result = {"invoice": inv, "amount": Decimal("0.00"), "external_id": ""}

    if not inv:
        return result

    external_id = ""
    amount_cents = None

    if session_or_intent.get("object") == "checkout.session":
        external_id = session_or_intent.get("payment_intent") or ""
        amount_cents = session_or_intent.get("amount_total")
    elif session_or_intent.get("object") == "payment_intent":
        external_id = session_or_intent.get("id") or ""
        amount_cents = session_or_intent.get("amount_received")

    paid = _record_payment(inv, amount_cents, external_id=external_id, method="Stripe")
    result.update({"amount": paid, "external_id": external_id})
    return result
    

@csrf_exempt
def webhook_stripe(request):
    payload = request.body
    sig = request.headers.get("Stripe-Signature", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, SignatureVerificationError):
        return HttpResponse(status=400)

    type_ = event.get("type")
    data = event["data"]["object"]
    event_id = event.get("id") or ""

    # Pre-create log record
    log = WebhookLog.objects.create(
        stripe_event_id=event_id,
        type=type_ or "",
        raw=event,
    )

    try:
        info = {"invoice": None, "amount": Decimal("0.00"), "external_id": ""}

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

        elif type_ in {"refund.succeeded"}:
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

# --- Handlers ---

def _handle_checkout_completed(session):
    # We expect mode=subscription
    customer_id = session.get("customer")
    subscription_id = session.get("subscription")
    meta = session.get("metadata") or {}
    company_id = meta.get("company_id")
    tier_slug = meta.get("tier_slug")
    if not (company_id and customer_id and subscription_id):
        return

    from core.models import Company
    try:
        company = Company.objects.get(id=company_id)
    except Company.DoesNotExist:
        return

    tier = SubscriptionTier.objects.filter(slug=tier_slug).first()
    sub, _ = CompanySubscription.objects.get_or_create(company=company)
    sub.tier = tier
    sub.stripe_customer_id = customer_id
    sub.stripe_subscription_id = subscription_id
    # Pull subscription to get status/period
    s = stripe.Subscription.retrieve(subscription_id)
    sub.status = s.status
    sub.current_period_end = timezone.datetime.fromtimestamp(s.current_period_end, tz=timezone.utc) # type: ignore
    sub.cancel_at_period_end = bool(getattr(s, "cancel_at_period_end", False))
    sub.save()


def _handle_subscription_event(s):
    subscription_id = s.get("id")
    status = s.get("status")
    current_period_end = s.get("current_period_end")
    cancel_at_period_end = s.get("cancel_at_period_end")

    try:
        sub = CompanySubscription.objects.get(stripe_subscription_id=subscription_id)
    except CompanySubscription.DoesNotExist:
        return

    from django.utils import timezone as tz
    sub.status = status
    if current_period_end:
        sub.current_period_end = tz.datetime.fromtimestamp(current_period_end, tz=tz.utc)
    sub.cancel_at_period_end = bool(cancel_at_period_end)
    sub.save()
    
    
def _find_invoice_from_metadata(meta: dict) -> Invoice | None:
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


def _record_payment(inv: Invoice, amount_cents: int | None, *, external_id: str = "", method: str = "Stripe"):
    if amount_cents is None:
        return Decimal("0.00")

    amount = (Decimal(amount_cents) / Decimal("100")).quantize(Decimal("0.01"))

    # Idempotency: avoid duplicate rows on Stripe retries
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
        pass

    return amount


@staff_member_required
def webhook_logs(request):
    logs = WebhookLog.objects.order_by("-created_at")[:200]
    return render(request, "billing/webhook_logs.html", {"logs": logs})


def _handle_refund_from_charge(charge: dict) -> dict:
    """
    Handle refund events from a Charge object (event types: charge.refunded, charge.refund.updated).
    Creates negative Payments for each refund (idempotent via external_id).
    """
    pi = charge.get("payment_intent") or ""
    refunds = (charge.get("refunds") or {}).get("data", [])
    found_inv = None
    last_amount = Decimal("0.00")
    last_ext_id = ""

    # Find the original positive payment by Payment.external_id == payment_intent_id
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
        amount = (Decimal(amt_cents) / Decimal("100")).quantize(Decimal("0.01"))
        ext = f"{pi}:refund:{refund_id}"

        # Idempotent negative Payment
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


def _handle_refund_from_refund(refund: dict) -> dict:
    """
    Handle refund.succeeded events (object is a Refund).
    """
    refund_id = refund.get("id") or ""
    charge_id = refund.get("charge") or ""
    amt_cents = refund.get("amount")
    amount = (Decimal(amt_cents or 0) / Decimal("100")).quantize(Decimal("0.01"))

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