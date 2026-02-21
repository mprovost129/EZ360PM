from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.http import HttpRequest

from audit.services import log_event
from companies.models import Company

from .models import CompanySubscription, PlanCode, BillingInterval, SubscriptionStatus, PlanCatalog, SeatAddonConfig
from .services import ensure_company_subscription


def stripe_enabled() -> bool:
    """True when subscription Checkout is configured (secret key + price map)."""
    return bool(getattr(settings, "STRIPE_SECRET_KEY", "") and getattr(settings, "STRIPE_PRICE_MAP", {}))


def stripe_portal_enabled() -> bool:
    """True when Stripe Billing Portal can be used (secret key only)."""
    return bool(getattr(settings, "STRIPE_SECRET_KEY", ""))


def _lazy_import_stripe():
    try:
        import stripe  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("Stripe is not installed. Run `pip install stripe` in your environment.") from e
    stripe.api_key = getattr(settings, "STRIPE_SECRET_KEY", "")
    return stripe


def _lookup_key_for_base(plan: str, interval: str) -> str:
    if plan not in {PlanCode.STARTER, PlanCode.PROFESSIONAL, PlanCode.PREMIUM}:
        raise ValueError("Invalid plan.")
    if interval not in {BillingInterval.MONTH, BillingInterval.YEAR}:
        raise ValueError("Invalid interval.")

    if plan == PlanCode.STARTER:
        if interval == BillingInterval.MONTH:
            return "ez360pm_starter_monthly"
        if interval == BillingInterval.YEAR:
            return "ez360pm_starter_yearly"
    elif plan == PlanCode.PROFESSIONAL:
        if interval == BillingInterval.MONTH:
            return "ez360pm_pro_monthly"
        if interval == BillingInterval.YEAR:
            return "ez360pm_pro_yearly"
    elif plan == PlanCode.PREMIUM:
        if interval == BillingInterval.MONTH:
            return "ez360pm_premium_monthly"
        if interval == BillingInterval.YEAR:
            return "ez360pm_premium_yearly"

    raise ValueError("Invalid plan/interval.")


def _lookup_key_for_seat(interval: str) -> str:
    if interval == BillingInterval.MONTH:
        return "ez360pm_seat_monthly"
    if interval == BillingInterval.YEAR:
        return "ez360pm_seat_yearly"
    raise ValueError("Invalid interval.")


def get_price_id_by_lookup_key(lookup_key: str) -> str:
    """
    Price lookup:

    - STRIPE_PRICE_MAP_JSON supports either:
      A) legacy keys: {"standard:solo": "price_..."}
      B) lookup keys: {"ez360pm_starter_monthly": "price_..."}
    """
    price_map: dict[str, str] = getattr(settings, "STRIPE_PRICE_MAP", {}) or {}
    return str(price_map.get(lookup_key, "")).strip()


def ensure_customer(subscription: CompanySubscription, company: Company) -> CompanySubscription:
    if subscription.stripe_customer_id:
        return subscription

    stripe = _lazy_import_stripe()
    customer = stripe.Customer.create(
        name=company.name,
        email=getattr(company, "billing_email", "") or "",
        metadata={
            "company_id": str(company.id),
            "product": "ez360pm",
        },
    )
    subscription.stripe_customer_id = str(customer["id"])
    subscription.save(update_fields=["stripe_customer_id", "updated_at"])
    return subscription


@dataclass(frozen=True)
class CheckoutSessionResult:
    id: str
    url: str


@dataclass(frozen=True)
class PortalSessionResult:
    url: str


def create_billing_portal_session(
    request: HttpRequest,
    *,
    company: Company,
) -> PortalSessionResult:
    """Create a Stripe Billing Portal session for the company's customer."""
    stripe = _lazy_import_stripe()
    sub = ensure_company_subscription(company)
    sub = ensure_customer(sub, company)

    return_url = request.build_absolute_uri("/billing/")
    portal_args = {
        "customer": sub.stripe_customer_id,
        "return_url": return_url,
    }
    configuration_id = str(getattr(settings, "STRIPE_PORTAL_CONFIGURATION_ID", "") or "").strip()
    if configuration_id:
        portal_args["configuration"] = configuration_id

    session = stripe.billing_portal.Session.create(**portal_args)

    log_event(
        company=company,
        actor=getattr(request, "active_employee", None),
        event_type="billing.stripe.portal_started",
        object_type="company",
        object_id=company.id,
        summary="Stripe customer portal opened.",
        payload={"stripe_portal_session_id": str(session.get("id", ""))},
        request=request,
    )
    return PortalSessionResult(url=str(session["url"]))


def create_subscription_checkout_session(
    request: HttpRequest,
    *,
    company: Company,
    plan: str,
    interval: str,
) -> CheckoutSessionResult:
    """
    Create a subscription Checkout session for base plan only.

    Extra seats are managed as a separate subscription item (quantity-based) later via:
    - portal OR
    - a dedicated "Manage seats" flow in EZ360PM (future pack).
    """
    plan_row = PlanCatalog.objects.filter(code=plan, is_active=True).first()
    price_id = ""
    if plan_row:
        if interval == BillingInterval.MONTH:
            price_id = str(plan_row.stripe_monthly_price_id or "").strip()
        elif interval == BillingInterval.YEAR:
            price_id = str(plan_row.stripe_annual_price_id or "").strip()

    if not price_id:
        lookup_key = _lookup_key_for_base(plan, interval)
        price_id = get_price_id_by_lookup_key(lookup_key)
    if not price_id:
        raise RuntimeError(f"Stripe price map is missing price_id for {lookup_key}.")

    stripe = _lazy_import_stripe()
    sub = ensure_company_subscription(company)
    sub = ensure_customer(sub, company)

    success_url = request.build_absolute_uri("/billing/?stripe=success")
    cancel_url = request.build_absolute_uri("/billing/?stripe=cancel")

    # Stripe-native trial (card first, then trial, then auto-renew)
    # - Checkout collects a payment method up front
    # - Subscription is created in `trialing` status
    # - Stripe charges automatically at trial end and renews thereafter
    trial_days = 14
    trial_days = 14
    # Prefer per-plan trial days from the DB catalog.
    try:
        plan_row = PlanCatalog.objects.filter(code=plan, is_active=True).first()
        if plan_row and getattr(plan_row, 'trial_days', None) is not None:
            trial_days = int(plan_row.trial_days)
    except Exception:
        pass

    # Fallback to Ops SiteConfig singleton (legacy control surface).
    if trial_days == 14:
        try:
            from ops.models import SiteConfig
            cfg = SiteConfig.get_solo()
            trial_days = int(getattr(cfg, "billing_trial_days", 14) or 14)
        except Exception:
            trial_days = int(getattr(settings, "EZ360PM_TRIAL_DAYS", 14) or 14)
    if trial_days < 0:
        trial_days = 0

    session = stripe.checkout.Session.create(
        mode="subscription",
        customer=sub.stripe_customer_id,
        line_items=[{"price": price_id, "quantity": 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        allow_promotion_codes=True,
        # Force payment method collection even if the first invoice is $0 due to a trial.
        payment_method_collection="always",
        subscription_data={
            "trial_period_days": trial_days,
            "metadata": {
                "company_id": str(company.id),
                "plan": plan,
                "interval": interval,
                "product": "ez360pm",
            }
        },
        metadata={
            "company_id": str(company.id),
            "plan": plan,
            "interval": interval,
            "product": "ez360pm",
        },
    )

    log_event(
        company=company,
        actor=getattr(request, "active_employee", None),
        event_type="billing.stripe.checkout_started",
        object_type="company",
        object_id=company.id,
        summary=f"Stripe checkout started ({plan}/{interval}).",
        payload={"stripe_session_id": str(session.get("id", ""))},
        request=request,
    )

    return CheckoutSessionResult(id=str(session["id"]), url=str(session["url"]))


def verify_and_construct_event(payload: bytes, sig_header: str | None) -> Any:
    stripe = _lazy_import_stripe()
    secret = getattr(settings, "STRIPE_WEBHOOK_SECRET", "") or ""
    if not secret:
        # If no secret is set, accept raw events (dev-only).
        return stripe.Event.construct_from(json.loads(payload.decode("utf-8")), stripe.api_key)
    return stripe.Webhook.construct_event(payload, sig_header, secret)



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
    extra_seats: int | None = None

    # Build reverse lookup by price_id (optional)
    price_map: dict[str, str] = {}
    try:
        price_map = dict(getattr(settings, "STRIPE_PRICE_MAP", {}) or {})
    except Exception:
        price_map = {}
    reverse_by_price_id = {v: k for k, v in price_map.items() if isinstance(v, str)}

    def _consume_lookup_key(lk: str, qty: int):
        nonlocal plan, interval, extra_seats
        if lk.startswith("ez360pm_seat_"):
            extra_seats = int(qty or 0)
            if lk.endswith("_monthly"):
                interval = interval or BillingInterval.MONTH
            elif lk.endswith("_annual"):
                interval = interval or BillingInterval.YEAR
            return

        if lk.startswith("ez360pm_starter_"):
            plan = plan or PlanCode.STARTER
            interval = interval or (BillingInterval.MONTH if lk.endswith("_monthly") else BillingInterval.YEAR)
            return
        if lk.startswith("ez360pm_pro_"):
            plan = plan or PlanCode.PROFESSIONAL
            interval = interval or (BillingInterval.MONTH if lk.endswith("_monthly") else BillingInterval.YEAR)
            return
        if lk.startswith("ez360pm_premium_"):
            plan = plan or PlanCode.PREMIUM
            interval = interval or (BillingInterval.MONTH if lk.endswith("_monthly") else BillingInterval.YEAR)
            return

    for item in items:
        price = (item.get("price") or {})
        lk = str(price.get("lookup_key") or "")
        pid = str(price.get("id") or "")
        qty = int(item.get("quantity") or 0)

        if lk:
            _consume_lookup_key(lk, qty)
            continue

        # Try reverse lookup by price id
        if pid and pid in reverse_by_price_id:
            _consume_lookup_key(reverse_by_price_id[pid], qty)

    return plan, interval, extra_seats


def fetch_and_sync_subscription_from_stripe(*, company: Company) -> None:
    """
    Staff operation: fetch current subscription from Stripe API and sync CompanySubscription.

    Requires billing Stripe secret key and stripe python package.
    """
    sub = ensure_company_subscription(company)
    if not sub.stripe_subscription_id:
        raise ValueError("Company has no stripe_subscription_id to fetch.")

    stripe = _lazy_import_stripe()
    stripe_sub = stripe.Subscription.retrieve(sub.stripe_subscription_id)

    plan, interval, extra_seats = _infer_from_subscription_object(dict(stripe_sub))
    status = str(stripe_sub.get("status") or "")

    current_period_start = stripe_sub.get("current_period_start")
    current_period_end = stripe_sub.get("current_period_end")

    trial_start = stripe_sub.get("trial_start")
    trial_end = stripe_sub.get("trial_end")

    # cancel flags
    cancel_at_period_end = bool(stripe_sub.get("cancel_at_period_end") or False)
    cancel_at = stripe_sub.get("cancel_at")
    canceled_at = stripe_sub.get("canceled_at")

    sync_subscription_from_stripe(
        company=company,
        stripe_customer_id=str(stripe_sub.get("customer") or ""),
        stripe_subscription_id=str(stripe_sub.get("id") or ""),
        plan=plan,
        interval=interval,
        extra_seats=extra_seats,
        status=status,
        current_period_start=int(current_period_start) if current_period_start else None,
        current_period_end=int(current_period_end) if current_period_end else None,
        trial_started_at=int(trial_start) if trial_start else None,
        trial_ends_at=int(trial_end) if trial_end else None,
        cancel_at_period_end=cancel_at_period_end,
        cancel_at=int(cancel_at) if cancel_at else None,
        canceled_at=int(canceled_at) if canceled_at else None,
    )


def sync_subscription_from_stripe(
    *,
    company: Company,
    stripe_customer_id: str = "",
    stripe_subscription_id: str = "",
    plan: str | None = None,
    interval: str | None = None,
    extra_seats: int | None = None,
    status: str | None = None,
    current_period_start: int | None = None,
    current_period_end: int | None = None,
    trial_started_at: int | None = None,
    trial_ends_at: int | None = None,
    cancel_at_period_end: bool | None = None,
    cancel_at: int | None = None,
    canceled_at: int | None = None,
) -> None:
    """
    Update CompanySubscription from Stripe webhook data.

    Stripe is the source of truth for:
    - subscription status
    - current period start/end
    - cancellation state
    - plan tier + interval (best-effort inference)
    - extra seat quantity (best-effort inference)
    """
    sub = ensure_company_subscription(company)
    old_status = sub.status

    changed: list[str] = []
    if stripe_customer_id and stripe_customer_id != sub.stripe_customer_id:
        sub.stripe_customer_id = stripe_customer_id
        changed.append("stripe_customer_id")
    if stripe_subscription_id and stripe_subscription_id != sub.stripe_subscription_id:
        sub.stripe_subscription_id = stripe_subscription_id
        changed.append("stripe_subscription_id")

    if plan and plan in {PlanCode.STARTER, PlanCode.PROFESSIONAL, PlanCode.PREMIUM} and plan != sub.plan:
        sub.plan = plan
        changed.append("plan")

    if interval and interval in {BillingInterval.MONTH, BillingInterval.YEAR} and interval != sub.billing_interval:
        sub.billing_interval = interval
        changed.append("billing_interval")

    if extra_seats is not None:
        v = max(0, int(extra_seats))
        if v != int(sub.extra_seats or 0):
            sub.extra_seats = v
            changed.append("extra_seats")

    if status:
        mapped = {
            "trialing": SubscriptionStatus.TRIALING,
            "active": SubscriptionStatus.ACTIVE,
            "past_due": SubscriptionStatus.PAST_DUE,
            "canceled": SubscriptionStatus.CANCELED,
            "unpaid": SubscriptionStatus.PAST_DUE,
            "incomplete_expired": SubscriptionStatus.ENDED,
            "incomplete": SubscriptionStatus.PAST_DUE,
        }.get(status, None)
        if mapped and mapped != sub.status:
            sub.status = mapped
            changed.append("status")

    from django.utils import timezone
    if current_period_start is not None:
        dt = timezone.datetime.fromtimestamp(int(current_period_start), tz=timezone.utc)
        sub.current_period_start = dt
        changed.append("current_period_start")
    if current_period_end is not None:
        dt = timezone.datetime.fromtimestamp(int(current_period_end), tz=timezone.utc)
        sub.current_period_end = dt
        changed.append("current_period_end")

    # Trial window (Stripe)
    if trial_started_at is not None:
        dt = timezone.datetime.fromtimestamp(int(trial_started_at), tz=timezone.utc)
        sub.trial_started_at = dt
        changed.append("trial_started_at")
    if trial_ends_at is not None:
        dt = timezone.datetime.fromtimestamp(int(trial_ends_at), tz=timezone.utc)
        sub.trial_ends_at = dt
        changed.append("trial_ends_at")

    # cancellation state (Stripe)
    if cancel_at_period_end is not None:
        sub.stripe_cancel_at_period_end = bool(cancel_at_period_end)
        changed.append("stripe_cancel_at_period_end")
    if cancel_at is not None:
        dt = timezone.datetime.fromtimestamp(int(cancel_at), tz=timezone.utc)
        sub.stripe_cancel_at = dt
        changed.append("stripe_cancel_at")
    if canceled_at is not None:
        dt = timezone.datetime.fromtimestamp(int(canceled_at), tz=timezone.utc)
        sub.stripe_canceled_at = dt
        changed.append("stripe_canceled_at")

    if changed:
        sub.save(update_fields=changed + ["updated_at"])

        # Ops notification: first time a subscription becomes ACTIVE.
        try:
            if old_status != SubscriptionStatus.ACTIVE and sub.status == SubscriptionStatus.ACTIVE and not getattr(sub, "ops_notified_active_at", None):
                from django.db import transaction
                from ops.services_notifications import notify_subscription_became_active

                def _on_commit():
                    try:
                        notify_subscription_became_active(company=company)
                    finally:
                        # mark as notified (best-effort)
                        try:
                            sub.ops_notified_active_at = timezone.now()
                            sub.save(update_fields=["ops_notified_active_at", "updated_at"])
                        except Exception:
                            pass

                transaction.on_commit(_on_commit)
        except Exception:
            pass
