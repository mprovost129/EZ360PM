# core/decorators.py
from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, Optional, TypeVar, cast

from django.contrib import messages
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone

from .utils import get_active_company

ViewFunc = TypeVar("ViewFunc", bound=Callable[..., HttpResponse])


def _safe_redirect_to_onboarding_or_home() -> HttpResponse:
    """
    Redirect to onboarding if available, otherwise fallback to dashboard home,
    and finally to root as a last resort.
    """
    try:
        return redirect("core:onboarding_company")
    except NoReverseMatch:
        try:
            return redirect("dashboard:home")
        except NoReverseMatch:
            return redirect("/")


def _has_active_subscription(company) -> bool:
    """
    Safe checker that avoids hard failures when billing is absent or partially configured.

    Rules:
      - Subscription must exist.
      - status in {"active", "trialing"} is treated as valid.
      - If cancel_at_period_end is True, the subscription is valid until current_period_end.
    """
    try:
        sub = getattr(company, "subscription", None)
        if not sub:
            return False

        status = (getattr(sub, "status", "") or "").lower()
        if status not in {"active", "trialing"}:
            return False

        # If cancellation at period end, still valid until then.
        if getattr(sub, "cancel_at_period_end", False):
            cpe = getattr(sub, "current_period_end", None)
            return bool(cpe and cpe > timezone.now())

        return True
    except Exception:
        # If anything unexpected happens, err on the safe side and treat as not active.
        return False


def require_subscription(view: ViewFunc) -> ViewFunc:
    """
    Guard a view so it's accessible only when the active company has an active subscription.
    If no active company is set, the user is redirected to onboarding (or dashboard/home).
    """
    @wraps(view)
    def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
        company = get_active_company(request)
        if not company:
            messages.info(request, "Create your company profile to continue.")
            return _safe_redirect_to_onboarding_or_home()

        if not _has_active_subscription(company):
            messages.warning(request, "Your subscription is inactive. Choose a plan to continue.")
            try:
                # Include a 'next' parameter when possible so users can return after checkout.
                return redirect(f"{reverse('billing:plans')}?next={request.path}")
            except NoReverseMatch:
                return _safe_redirect_to_onboarding_or_home()

        return view(request, *args, **kwargs)

    return cast(ViewFunc, _wrapped)


def subscription_or_landing(
    template_name: str,
    *,
    context: Optional[Dict[str, Any]] = None,
    context_cb: Optional[Callable[[HttpRequest], Dict[str, Any]]] = None,
) -> Callable[[ViewFunc], ViewFunc]:
    """
    Decorator that:
      - Executes the view if the active company has an active subscription.
      - Otherwise renders a friendly landing page (HTTP 200), optionally enriched via `context_cb`.

    Useful for top-level pages where you want to showcase the product and prompt for upgrade
    rather than hard-blocking with a redirect.
    """
    base_context: Dict[str, Any] = context or {}

    def _decorator(view_func: ViewFunc) -> ViewFunc:
        @wraps(view_func)
        def _wrapped(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            company = get_active_company(request)
            if company and _has_active_subscription(company):
                return view_func(request, *args, **kwargs)

            landing_ctx = dict(base_context)
            if context_cb:
                try:
                    landing_ctx.update(context_cb(request) or {})
                except Exception:
                    # If your callback throws, don’t break the page—just show base context.
                    pass

            return render(request, template_name, landing_ctx, status=200)

        return cast(ViewFunc, _wrapped)

    return _decorator
