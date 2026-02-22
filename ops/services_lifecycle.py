from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from companies.models import Company
from billing.models import CompanySubscription, SubscriptionStatus

from .models import CompanyLifecycleEvent, LifecycleEventType


@dataclass(frozen=True)
class _SubState:
    status: str
    cancel_at_period_end: bool
    trial_ends_at_iso: str


def _state_from_sub(sub: CompanySubscription | None) -> _SubState:
    if not sub:
        return _SubState(status="", cancel_at_period_end=False, trial_ends_at_iso="")
    return _SubState(
        status=str(sub.status or ""),
        cancel_at_period_end=bool(getattr(sub, "stripe_cancel_at_period_end", False)),
        trial_ends_at_iso=(sub.trial_ends_at.isoformat() if getattr(sub, "trial_ends_at", None) else ""),
    )


def _emit(
    *,
    company: Company,
    event_type: str,
    stripe_event_id: str = "",
    occurred_at=None,
    details: dict | None = None,
) -> None:
    """Best-effort lifecycle event creation with idempotency by stripe_event_id+type."""
    try:
        occurred_at = occurred_at or timezone.now()
        stripe_event_id = (stripe_event_id or "").strip()[:120]
        event_type = str(event_type)

        if stripe_event_id:
            exists = CompanyLifecycleEvent.objects.filter(
                company=company,
                event_type=event_type,
                stripe_event_id=stripe_event_id,
            ).exists()
            if exists:
                return

        CompanyLifecycleEvent.objects.create(
            occurred_at=occurred_at,
            company=company,
            event_type=event_type,
            stripe_event_id=stripe_event_id,
            details=details or {},
        )
    except Exception:
        return


def record_subscription_transition(
    *,
    company: Company,
    old_sub: CompanySubscription | None,
    new_sub: CompanySubscription | None,
    stripe_event_id: str = "",
    occurred_at=None,
    details: dict | None = None,
) -> None:
    """Record first-class lifecycle events from a mirrored Stripe subscription transition."""

    old = _state_from_sub(old_sub)
    new = _state_from_sub(new_sub)

    if not new.status:
        return

    occurred_at = occurred_at or timezone.now()

    old_status = old.status
    new_status = new.status

    # Trial started: any transition into TRIALING (from non-trialing), with a Stripe trial end.
    if old_status != SubscriptionStatus.TRIALING and new_status == SubscriptionStatus.TRIALING and new.trial_ends_at_iso:
        _emit(
            company=company,
            event_type=LifecycleEventType.TRIAL_STARTED,
            stripe_event_id=stripe_event_id,
            occurred_at=occurred_at,
            details={"old": old.__dict__, "new": new.__dict__, **(details or {})},
        )

    # Trial converted: TRIALING -> ACTIVE.
    if old_status == SubscriptionStatus.TRIALING and new_status == SubscriptionStatus.ACTIVE:
        _emit(
            company=company,
            event_type=LifecycleEventType.TRIAL_CONVERTED,
            stripe_event_id=stripe_event_id,
            occurred_at=occurred_at,
            details={"old": old.__dict__, "new": new.__dict__, **(details or {})},
        )

    # Subscription started: non-active (not trialing) -> ACTIVE.
    if old_status not in {SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIALING} and new_status == SubscriptionStatus.ACTIVE:
        _emit(
            company=company,
            event_type=LifecycleEventType.SUBSCRIPTION_STARTED,
            stripe_event_id=stripe_event_id,
            occurred_at=occurred_at,
            details={"old": old.__dict__, "new": new.__dict__, **(details or {})},
        )

    # Subscription canceled: transition into canceled/ended.
    if new_status in {SubscriptionStatus.CANCELED, SubscriptionStatus.ENDED} and old_status not in {SubscriptionStatus.CANCELED, SubscriptionStatus.ENDED}:
        _emit(
            company=company,
            event_type=LifecycleEventType.SUBSCRIPTION_CANCELED,
            stripe_event_id=stripe_event_id,
            occurred_at=occurred_at,
            details={"old": old.__dict__, "new": new.__dict__, **(details or {})},
        )

    # Reactivated: canceled/ended/past_due -> active, OR cancel_at_period_end removed while active.
    if (
        old_status in {SubscriptionStatus.CANCELED, SubscriptionStatus.ENDED, SubscriptionStatus.PAST_DUE}
        and new_status == SubscriptionStatus.ACTIVE
    ) or (
        old_status == SubscriptionStatus.ACTIVE
        and new_status == SubscriptionStatus.ACTIVE
        and old.cancel_at_period_end
        and not new.cancel_at_period_end
    ):
        _emit(
            company=company,
            event_type=LifecycleEventType.SUBSCRIPTION_REACTIVATED,
            stripe_event_id=stripe_event_id,
            occurred_at=occurred_at,
            details={"old": old.__dict__, "new": new.__dict__, **(details or {})},
        )
