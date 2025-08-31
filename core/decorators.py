# core/decorators.py
from functools import wraps
from django.shortcuts import redirect, render
from django.contrib import messages
from .utils import get_active_company
from django.utils import timezone
from typing import Callable, Optional, Dict, Any


def require_subscription(view):
    @wraps(view)
    def _wrapped(request, *args, **kwargs):
        company = get_active_company(request)
        sub = getattr(company, "subscription", None) if company else None
        if not sub or not sub.is_active():
            messages.warning(request, "Your subscription is inactive. Choose a plan to continue.")
            return redirect("billing:plans")
        return view(request, *args, **kwargs)
    return _wrapped


def _has_active_subscription(company) -> bool:
    """
    Safe checker that doesn't hard-crash if billing isn't installed.
    """
    try:
        sub = getattr(company, "subscription", None)
        if not sub:
            return False
        # Treat Active/Trialing as valid
        status_ok = str(sub.status or "").lower() in {"active", "trialing"}
        if not status_ok:
            return False
        if sub.cancel_at_period_end:
            # still good until period end
            return bool(sub.current_period_end and sub.current_period_end > timezone.now())
        return True
    except Exception:
        return False

def subscription_or_landing(
    template_name: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    context_cb: Optional[Callable] = None,
):
    """
    If the active company has a subscription: run the view.
    Otherwise: render a friendly landing page (no 403).
    """
    context = context or {}

    def _decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            company = get_active_company(request)
            if company and _has_active_subscription(company):
                return view_func(request, *args, **kwargs)
            landing_ctx = dict(context)
            if context_cb:
                landing_ctx.update(context_cb(request) or {})
            return render(request, template_name, landing_ctx, status=200)
        return _wrapped
    return _decorator
