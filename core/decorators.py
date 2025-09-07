# core/decorators.py
from __future__ import annotations

from functools import wraps
from typing import Callable, Optional, Dict, Any, TypeVar

from django.conf import settings
from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone

# Prefer the lightweight helper from core.utils; provide a safe fallback.
try:
    from core.utils import user_has_active_subscription  # type: ignore
except Exception:  # pragma: no cover
    def user_has_active_subscription(company) -> bool:  # fallback
        return False

# Feature flag to allow turning off gating in dev/tests.
ENFORCE_SUBSCRIPTION: bool = bool(getattr(settings, "ENFORCE_SUBSCRIPTION", True))

VF = TypeVar("VF", bound=Callable[..., HttpResponse])

__all__ = [
    "require_subscription",
    "subscription_or_landing",
]


def require_subscription(view_func: VF) -> VF:
    """
    Guard views behind an active subscription.
    - If settings.ENFORCE_SUBSCRIPTION is False, always allow.
    - If the user’s active company has an active/trialing subscription, allow.
    - Otherwise, redirect to billing plans with a friendly message.
    """
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        # Lazy imports to avoid circular import with company.utils
        from django.conf import settings
        from company.utils import get_active_company

        enforce = getattr(settings, "ENFORCE_SUBSCRIPTION", True)
        if not enforce:
            return view_func(request, *args, **kwargs)

        company = get_active_company(request)
        # user_has_active_subscription is defined in this module; no import needed
        if company and user_has_active_subscription(company):
            return view_func(request, *args, **kwargs)

        messages.warning(request, "Please choose a plan to use this feature.")
        return redirect("billing:plans")

    return _wrapped  # type: ignore[return-value]


def _has_active_subscription(company) -> bool:
    """
    Safe checker that doesn't hard-crash if billing isn't installed and
    tolerates partially-populated subscription objects.
    """
    try:
        sub = getattr(company, "subscription", None)
        if not sub:
            return False
        status_ok = str(getattr(sub, "status", "")).lower() in {"active", "trialing"}
        if not status_ok:
            return False
        # If set to cancel at period end, still valid until the end timestamp.
        if getattr(sub, "cancel_at_period_end", False):
            end = getattr(sub, "current_period_end", None)
            return bool(end and end > timezone.now())
        return True
    except Exception:
        return False


def subscription_or_landing(
    template_name: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    context_cb: Optional[Callable[[HttpRequest], Dict[str, Any]]] = None,
):
    """
    Decorator factory:
      If the active company has a subscription → run the view.
      Otherwise → render a friendly landing page (HTTP 200, not 403).

    Args:
        template_name: Path to the landing template.
        context: Static context dict merged into the landing render.
        context_cb: Optional callback(request) → dict for dynamic context.
    """
    base_ctx = dict(context or {})

    def _decorator(view_func: VF) -> VF:
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            # Lazy imports to prevent circular import with company.utils
            from django.conf import settings
            from company.utils import get_active_company
            # user_has_active_subscription is defined in this module

            # If enforcement is disabled, always allow
            if not getattr(settings, "ENFORCE_SUBSCRIPTION", True):
                return view_func(request, *args, **kwargs)

            company = get_active_company(request)
            if company and user_has_active_subscription(company):
                return view_func(request, *args, **kwargs)

            landing_ctx = dict(base_ctx)
            if context_cb:
                try:
                    landing_ctx.update(context_cb(request) or {})
                except Exception:
                    # Don’t block landing if the callback fails.
                    pass

            return render(request, template_name, landing_ctx, status=200)

        return _wrapped  # type: ignore[return-value]

    return _decorator