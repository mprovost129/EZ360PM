# billing/utils.py
from functools import wraps
from django.contrib import messages
from django.shortcuts import redirect
from core.utils import get_active_company
from .models import SubscriptionTier
from typing import Tuple

def _ctx(request) -> Tuple[object, object, object]:
    """Return (company, subscription, tier) for convenience."""
    company = get_active_company(request)
    sub = getattr(company, "subscription", None) if company else None
    tier = getattr(sub, "tier", None) if sub else None
    return company, sub, tier

def company_has_feature(company, key: str) -> bool:
    sub = getattr(company, "subscription", None)
    tier = getattr(sub, "tier", None)
    return bool(sub and sub.is_active() and tier and (tier.features or {}).get(key, False))

def require_feature(key: str):
    """Require an active sub AND that the tier enables `key`. Redirects to plans with a flash otherwise."""
    def deco(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            company, sub, tier = _ctx(request)
            if not (sub and sub.is_active()): # type: ignore
                messages.warning(request, "Your subscription is inactive. Choose a plan to continue.")
                return redirect("billing:plans")
            if not company_has_feature(company, key):
                messages.warning(request, "This feature is available on a higher plan.")
                return redirect("billing:plans")
            return view(request, *args, **kwargs)
        return _wrapped
    return deco

def require_tier_at_least(min_slug: str):
    """Require an active sub whose tier.sort >= target.sort."""
    def deco(view):
        @wraps(view)
        def _wrapped(request, *args, **kwargs):
            company, sub, tier = _ctx(request)
            if not (sub and sub.is_active()): # type: ignore
                messages.warning(request, "Your subscription is inactive. Choose a plan to continue.")
                return redirect("billing:plans")
            target = SubscriptionTier.objects.filter(slug=min_slug).first()
            if not (tier and target and tier.sort >= target.sort): # type: ignore
                messages.warning(request, "Upgrade your plan to access this feature.")
                return redirect("billing:plans")
            return view(request, *args, **kwargs)
        return _wrapped
    return deco

def enforce_limit_or_upsell(company, key: str, current_count: int):
    """Return (ok, limit). Block creates when plan cap is hit; caller handles redirect/flash."""
    sub = getattr(company, "subscription", None)
    tier = getattr(sub, "tier", None)
    limit = (tier.limits or {}).get(key) if (tier and tier.limits) else None
    if limit is not None and current_count >= int(limit):
        return False, int(limit)
    return True, limit






