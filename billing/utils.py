# billing/utils.py
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, Tuple, TypeVar, Any, cast

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse

from core.models import Company  # adjust import path if different
from core.utils import get_active_company
from .models import CompanySubscription, SubscriptionTier

ViewFunc = TypeVar("ViewFunc", bound=Callable[..., HttpResponse])


def _ctx(request: HttpRequest) -> Tuple[Optional[Company], Optional[CompanySubscription], Optional[SubscriptionTier]]:
    """Return (company, subscription, tier) for convenience."""
    company = get_active_company(request)
    sub = cast(Optional[CompanySubscription], getattr(company, "subscription", None)) if company else None
    tier = cast(Optional[SubscriptionTier], getattr(sub, "tier", None)) if sub else None
    return company, sub, tier


def _plans_url() -> str:
    # Keep one place to control the plans route
    return reverse("billing:plans")


def company_has_feature(company: Optional[Company], key: str) -> bool:
    """True if company has an active subscription and the tier enables `key`."""
    if not company:
        return False
    sub = cast(Optional[CompanySubscription], getattr(company, "subscription", None))
    if not (sub and sub.is_active()):
        return False
    tier = cast(Optional[SubscriptionTier], getattr(sub, "tier", None))
    if not tier or not isinstance(tier.features, dict):
        return False
    return bool(tier.features.get(key, False))


def require_feature(key: str) -> Callable[[ViewFunc], ViewFunc]:
    """
    Decorator: require an active subscription AND that the tier enables `key`.
    Redirects to plans with a flash otherwise.
    """
    def deco(view: ViewFunc) -> ViewFunc:
        @wraps(view)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            company, sub, _tier = _ctx(request)
            if not (sub and sub.is_active()):
                messages.warning(request, "Your subscription is inactive. Choose a plan to continue.")
                return redirect(_plans_url())
            if not company_has_feature(company, key):
                messages.warning(request, "This feature is available on a higher plan.")
                return redirect(_plans_url())
            return view(request, *args, **kwargs)
        return cast(ViewFunc, _wrapped)
    return deco


def require_tier_at_least(min_slug: str) -> Callable[[ViewFunc], ViewFunc]:
    """
    Decorator: require an active subscription whose tier.sort >= target.sort.
    """
    def deco(view: ViewFunc) -> ViewFunc:
        @wraps(view)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            _company, sub, tier = _ctx(request)
            if not (sub and sub.is_active()):
                messages.warning(request, "Your subscription is inactive. Choose a plan to continue.")
                return redirect(_plans_url())

            target = SubscriptionTier.objects.filter(slug=min_slug).first()
            if not (tier and target and tier.sort >= target.sort):
                messages.warning(request, "Upgrade your plan to access this feature.")
                return redirect(_plans_url())

            return view(request, *args, **kwargs)
        return cast(ViewFunc, _wrapped)
    return deco


def enforce_limit_or_upsell(company: Optional[Company], key: str, current_count: int) -> Tuple[bool, Optional[int]]:
    """
    Return (ok, limit). If the plan sets a cap for `key` and it's reached,
    returns (False, limit). Caller decides how to respond (flash/redirect).
    """
    if not company:
        return False, None

    sub = cast(Optional[CompanySubscription], getattr(company, "subscription", None))
    tier = cast(Optional[SubscriptionTier], getattr(sub, "tier", None)) if sub else None
    limits = tier.limits if (tier and isinstance(tier.limits, dict)) else None

    limit_val = limits.get(key) if limits else None
    try:
        limit_int = int(limit_val) if limit_val is not None else None
    except (TypeError, ValueError):
        limit_int = None

    if limit_int is not None and current_count >= limit_int:
        return False, limit_int
    return True, limit_int
