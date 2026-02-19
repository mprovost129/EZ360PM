from __future__ import annotations

import logging

from django.http import HttpRequest, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt

from companies.models import Company

from .models import BillingWebhookEvent, PlanCode, BillingInterval
from .stripe_service import sync_subscription_from_stripe, verify_and_construct_event, get_price_id_by_lookup_key


logger = logging.getLogger(__name__)


def _alert_webhook_failure(subject: str, message: str, *, extra: dict | None = None) -> None:
    """Best-effort ops alert for webhook failures."""
    try:
        from django.conf import settings
        if not getattr(settings, "EZ360_ALERT_ON_WEBHOOK_FAILURE", False):
            return
        from core.ops_alerts import alert_admins
        alert_admins(subject, message, extra=extra)
    except Exception:
        return


def _record_ops_alert(*, title: str, message: str, details: dict | None = None, company: Company | None = None) -> None:
    """Best-effort DB alert for staff ops console."""
    try:
        from ops.services_alerts import create_ops_alert
        from ops.models import OpsAlertLevel, OpsAlertSource

        create_ops_alert(
            title=title,
            message=message,
            level=OpsAlertLevel.ERROR,
            source=OpsAlertSource.STRIPE_WEBHOOK,
            company=company,
            details=details or {},
        )
    except Exception:
        return


def _infer_from_subscription_object(data_object: dict) -> tuple[str | None, str | None, int | None]:
    """
    Best-effort inference for (plan, interval, extra_seats) from Stripe subscription payload.

    Priority order:
    1) subscription.metadata.plan / subscription.metadata.interval
    2) subscription items price.lookup_key matching our recommended lookup keys
    3) subscription items price.id matching STRIPE_PRICE_MAP (reverse lookup by price_id)
    """
    meta = dict(data_object.get("metadata") or {})
    plan = meta.get("plan") or None
    interval = meta.get("interval") or None

    items = (data_object.get("items") or {}).get("data") or []
    extra_seats = None

    # Build reverse lookup by price_id (optional)
    price_map: dict[str, str] = {}
    try:
        from django.conf import settings
        price_map = dict(getattr(settings, "STRIPE_PRICE_MAP", {}) or {})
    except Exception:
        price_map = {}
    reverse_by_price_id = {v: k for k, v in price_map.items() if isinstance(v, str)}

    def _consume_lookup_key(lk: str, qty: int):
        nonlocal plan, interval, extra_seats
        if lk.startswith("ez360pm_seat_"):
            extra_seats = int(qty or 0)
            # interval can be inferred from seat lookup too
            if lk.endswith("_monthly"):
                interval = interval or BillingInterval.MONTH
            elif lk.endswith("_annual"):
                interval = interval or BillingInterval.YEAR
            return

        if lk.startswith("ez360pm_starter_"):
            plan = plan or PlanCode.STARTER
        elif lk.startswith("ez360pm_pro_"):
            plan = plan or PlanCode.PROFESSIONAL
        elif lk.startswith("ez360pm_premium_"):
            plan = plan or PlanCode.PREMIUM

        if lk.endswith("_monthly"):
            interval = interval or BillingInterval.MONTH
        elif lk.endswith("_annual"):
            interval = interval or BillingInterval.YEAR

    for it in items:
        qty = int(it.get("quantity") or 0)
        price = it.get("price") or {}
        lk = str(price.get("lookup_key") or "").strip()
        if lk:
            _consume_lookup_key(lk, qty)
            continue

        # fallback: map by price id -> lookup key
        pid = str(price.get("id") or "").strip()
        if pid and pid in reverse_by_price_id:
            _consume_lookup_key(reverse_by_price_id[pid], qty)

    # extra_seats default to 0 if we know there is no seat line item
    if extra_seats is None:
        extra_seats = 0

    return plan, interval, extra_seats


@csrf_exempt
def stripe_webhook(request: HttpRequest) -> HttpResponse:
    payload = request.body or b""
    sig = request.headers.get("Stripe-Signature")

    try:
        event = verify_and_construct_event(payload, sig)
    except Exception as e:
        logger.exception("stripe_webhook_signature_invalid err=%s", str(e)[:500])
        _record_ops_alert(
            title="Stripe webhook signature invalid",
            message="A Stripe webhook was received but signature validation failed.",
            details={"error": str(e)[:500]},
        )
        _alert_webhook_failure(
            "EZ360PM: Stripe webhook signature invalid",
            "A Stripe webhook was received but signature validation failed.",
            extra={"error": str(e)[:500]},
        )
        return HttpResponse(status=400)

    event_id = str(getattr(event, "id", "") or event.get("id", ""))
    event_type = str(getattr(event, "type", "") or event.get("type", ""))

    if not event_id:
        return HttpResponse(status=400)

    obj, created = BillingWebhookEvent.objects.get_or_create(
        stripe_event_id=event_id,
        defaults={"event_type": event_type, "payload_json": dict(event)},
    )
    if not created and obj.processed_at:
        return HttpResponse(status=200)

    ok = False
    error = ""

    try:
        data_object = event["data"]["object"]

        # Prefer metadata.company_id whenever present.
        metadata = dict(getattr(data_object, "metadata", None) or data_object.get("metadata", {}) or {})
        company_id = metadata.get("company_id") or ""

        company = None
        if company_id:
            company = Company.objects.filter(id=company_id).first()

        # Fallback: match by Stripe customer id already stored.
        if not company:
            cust = str(data_object.get("customer") or "")
            if cust:
                company = Company.objects.filter(subscription__stripe_customer_id=cust).first()

        if company:
            if event_type in {"checkout.session.completed"}:
                # Either: invoice payment checkout OR subscription checkout.
                invoice_id = (metadata.get("invoice_id") or "").strip()

                if invoice_id:
                    # Customer paid an invoice.
                    try:
                        from documents.models import Document, DocumentType, DocumentStatus
                        from payments.models import Payment, PaymentStatus, PaymentMethod
                        from payments.services import apply_payment_and_recalc

                        inv = Document.objects.filter(id=invoice_id, company=company, doc_type=DocumentType.INVOICE).first()
                        if inv and not inv.deleted_at:
                            session_id = str(data_object.get("id") or "")
                            payment_intent = str(data_object.get("payment_intent") or "")
                            amount_total = int(data_object.get("amount_total") or 0)

                            # Idempotency: do not create duplicate Payment rows for the same checkout session.
                            existing = None
                            if session_id:
                                existing = Payment.objects.filter(company=company, stripe_checkout_session_id=session_id).first()

                            if not existing:
                                p = Payment.objects.create(
                                    company=company,
                                    client=inv.client,
                                    invoice=inv,
                                    payment_date=timezone.now().date(),
                                    method=PaymentMethod.STRIPE,
                                    amount_cents=amount_total,
                                    status=PaymentStatus.SUCCEEDED,
                                    stripe_checkout_session_id=session_id,
                                    stripe_payment_intent_id=payment_intent,
                                )
                                apply_payment_and_recalc(p, actor=None)

                            # Defensive status update (apply_payment_and_recalc should set correctly)
                            if inv.status != DocumentStatus.PAID and int(inv.balance_due_cents or 0) <= 0:
                                inv.status = DocumentStatus.PAID
                                inv.save(update_fields=["status", "updated_at"])
                    except Exception:
                        # Keep webhook processing resilient; record failure via outer handler.
                        raise

                else:
                    # subscription created/confirmed via checkout
                    plan = (metadata.get("plan") or "").strip() or None
                    interval = (metadata.get("interval") or "").strip() or None
                    stripe_customer_id = str(data_object.get("customer") or "")
                    stripe_subscription_id = str(data_object.get("subscription") or "")
                    sync_subscription_from_stripe(
                        company=company,
                        stripe_customer_id=stripe_customer_id,
                        stripe_subscription_id=stripe_subscription_id,
                        plan=plan,
                        interval=interval,
                        status="active",
                    )

            elif event_type in {"customer.subscription.created", "customer.subscription.updated"}:
                stripe_customer_id = str(data_object.get("customer") or "")
                stripe_subscription_id = str(data_object.get("id") or "")
                status = str(data_object.get("status") or "")
                current_period_start = data_object.get("current_period_start")
                current_period_end = data_object.get("current_period_end")

                plan, interval, extra_seats = _infer_from_subscription_object(dict(data_object))

                sync_subscription_from_stripe(
                    company=company,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    plan=plan,
                    interval=interval,
                    extra_seats=extra_seats,
                    status=status or None,
                    current_period_start=current_period_start,
                    current_period_end=current_period_end,
                    cancel_at_period_end=bool(data_object.get("cancel_at_period_end") or False),
                    cancel_at=data_object.get("cancel_at"),
                    canceled_at=data_object.get("canceled_at"),
                )

            elif event_type in {"customer.subscription.deleted"}:
                stripe_customer_id = str(data_object.get("customer") or "")
                stripe_subscription_id = str(data_object.get("id") or "")
                sync_subscription_from_stripe(
                    company=company,
                    stripe_customer_id=stripe_customer_id,
                    stripe_subscription_id=stripe_subscription_id,
                    status="canceled",
                    cancel_at_period_end=False,
                    canceled_at=data_object.get("canceled_at"),
                )

            elif event_type in {"invoice.payment_failed"}:
                stripe_customer_id = str(data_object.get("customer") or "")
                sync_subscription_from_stripe(company=company, stripe_customer_id=stripe_customer_id, status="past_due")

            elif event_type in {"invoice.payment_succeeded"}:
                stripe_customer_id = str(data_object.get("customer") or "")
                sync_subscription_from_stripe(company=company, stripe_customer_id=stripe_customer_id, status="active")

        ok = True

    except Exception as e:
        ok = False
        error = str(e)[:5000]
        logger.exception("stripe_webhook_processing_failed event_id=%s type=%s err=%s", event_id, event_type, str(e)[:500])
        _record_ops_alert(
            title="Stripe webhook processing failed",
            message="A Stripe webhook was received but processing raised an exception.",
            details={"event_id": event_id, "event_type": event_type, "error": str(e)[:500]},
            company=company if 'company' in locals() else None,
        )
        _alert_webhook_failure(
            "EZ360PM: Stripe webhook processing failed",
            "A Stripe webhook was received but processing raised an exception.",
            extra={"event_id": event_id, "event_type": event_type, "error": str(e)[:500]},
        )
        try:
            import sentry_sdk
            sentry_sdk.capture_exception(e)
        except Exception:
            pass

    obj.event_type = event_type
    obj.ok = ok
    obj.error = error
    obj.processed_at = timezone.now()
    if not obj.payload_json:
        try:
            obj.payload_json = dict(event)
        except Exception:
            pass
    obj.save(update_fields=["event_type", "ok", "error", "processed_at", "payload_json"])

    return HttpResponse(status=200 if ok else 500)
