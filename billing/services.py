from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from companies.models import Company, EmployeeProfile

from .models import CompanySubscription, PlanCode, BillingInterval, SubscriptionStatus


# ------------------------------
# Plan tiers / included seats
# ------------------------------
PLAN_RANK: dict[str, int] = {
    PlanCode.STARTER: 1,
    PlanCode.PROFESSIONAL: 2,
    PlanCode.PREMIUM: 3,
}

INCLUDED_SEATS: dict[str, int] = {
    PlanCode.STARTER: 1,
    PlanCode.PROFESSIONAL: 5,
    PlanCode.PREMIUM: 10,
}


# ------------------------------
# Features by tier
# ------------------------------
# NOTE: Keep these feature codes stable — used across decorators/templates/tests.
FEATURE_ACCOUNTING_ENGINE = "accounting_engine"          # Professional+
FEATURE_ADVANCED_REPORTS = "advanced_reports"            # Premium
FEATURE_CUSTOM_DASHBOARDS = "custom_dashboards"          # Premium
FEATURE_ADVANCED_AUDIT = "advanced_audit"                # Premium (future)
FEATURE_API_ACCESS = "api_access"                        # Premium (future)
FEATURE_DROPBOX = "dropbox_integration"                  # Premium (future)


@dataclass(frozen=True)
class SubscriptionSummary:
    plan: str
    billing_interval: str
    status: str
    is_comped: bool
    comped_until: timezone.datetime | None
    discount_percent: int
    discount_is_active: bool
    is_trial: bool
    is_active_or_trial: bool
    trial_ends_at: timezone.datetime | None
    seats_used: int
    seats_included: int
    extra_seats: int
    seats_limit: int
    seats_remaining: int


def _trial_days() -> int:
    return int(getattr(settings, "EZ360PM_TRIAL_DAYS", 14) or 14)


def get_or_create_company_subscription(company: Company) -> CompanySubscription:
    """Return the singleton subscription row for a company (create if missing)."""
    sub, _ = CompanySubscription.objects.get_or_create(company=company)
    return sub


def ensure_trial_initialized(subscription: CompanySubscription) -> CompanySubscription:
    """Initialize trial start/end if subscription is trialing and dates not set."""
    if subscription.status != SubscriptionStatus.TRIALING:
        return subscription

    now = timezone.now()
    changed = False
    if not subscription.trial_started_at:
        subscription.trial_started_at = now
        changed = True
    if not subscription.trial_ends_at:
        subscription.trial_ends_at = now + timedelta(days=_trial_days())
        changed = True
    if changed:
        subscription.save(update_fields=["trial_started_at", "trial_ends_at", "updated_at"])
    return subscription


def ensure_company_subscription(company: Company) -> CompanySubscription:
    """Idempotently ensure a subscription exists and trial dates are set."""
    with transaction.atomic():
        sub = get_or_create_company_subscription(company)
        sub = ensure_trial_initialized(sub)
    return sub


def seats_used_for(company: Company) -> int:
    return int(EmployeeProfile.objects.filter(company=company, deleted_at__isnull=True, is_active=True).count())


def included_seats_for(plan: str) -> int:
    return int(INCLUDED_SEATS.get(plan, 1))


def seats_limit_for(subscription: CompanySubscription) -> int:
    included = included_seats_for(subscription.plan)
    extra = int(subscription.extra_seats or 0)
    return max(1, included + extra)


def build_subscription_summary(company: Company) -> SubscriptionSummary:
    sub = ensure_company_subscription(company)
    used = seats_used_for(company)
    included = included_seats_for(sub.plan)
    extra = int(sub.extra_seats or 0)
    limit_ = seats_limit_for(sub)
    remaining = max(0, limit_ - used)

    return SubscriptionSummary(
        plan=sub.plan,
        billing_interval=sub.billing_interval,
        status=sub.status,
        is_comped=sub.is_comped_active(),
        comped_until=sub.comped_until,
        discount_percent=int(sub.discount_percent or 0),
        discount_is_active=sub.discount_is_active(),
        is_trial=sub.is_in_trial(),
        is_active_or_trial=sub.is_active_or_trial(),
        trial_ends_at=sub.trial_ends_at,
        seats_used=used,
        seats_included=included,
        extra_seats=extra,
        seats_limit=limit_,
        seats_remaining=remaining,
    )


def company_is_locked(company: Company) -> bool:
    """Locked means: NOT active subscription AND NOT in trial."""
    sub = ensure_company_subscription(company)
    return not sub.is_active_or_trial()


def can_add_seat(company: Company) -> bool:
    """True if company has remaining seats under included + extra seats."""
    summary = build_subscription_summary(company)
    return summary.seats_used < summary.seats_limit


def plan_meets(plan: str, *, min_plan: str) -> bool:
    """True if plan rank >= min_plan rank."""
    return int(PLAN_RANK.get(plan, 0)) >= int(PLAN_RANK.get(min_plan, 0))


def plan_allows_feature(plan: str, feature_code: str) -> bool:
    """Central place to evolve feature gating rules."""
    # Accounting included in Professional+
    if feature_code == FEATURE_ACCOUNTING_ENGINE:
        return plan_meets(plan, min_plan=PlanCode.PROFESSIONAL)

    # Premium-only bundle (some are future, but we gate consistently now)
    premium_only = {
        FEATURE_ADVANCED_REPORTS,
        FEATURE_CUSTOM_DASHBOARDS,
        FEATURE_ADVANCED_AUDIT,
        FEATURE_API_ACCESS,
        FEATURE_DROPBOX,
    }
    if feature_code in premium_only:
        return plan_meets(plan, min_plan=PlanCode.PREMIUM)

    # Default: available to all tiers
    return True
