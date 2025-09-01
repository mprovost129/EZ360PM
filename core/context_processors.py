# core/context_processors.py
from __future__ import annotations

from typing import Dict, Any

from django.conf import settings
from django.http import HttpRequest

from .utils import get_active_company, user_has_active_subscription
from .services import unread_count


# -------------------------------------------------------------------
# Internal helpers
# -------------------------------------------------------------------

def _compute_app_frame(request: HttpRequest) -> Dict[str, Any]:
    """
    Centralized computation for commonly-needed frame context:
      - active_company
      - is_subscribed
      - unread_notifications_count

    Safe against missing billing app or unusual states.
    """
    user = getattr(request, "user", None)
    active_company = None
    is_subscribed = False
    unread = 0

    if getattr(user, "is_authenticated", False):
        try:
            active_company = get_active_company(request)
        except Exception:
            active_company = None

        if active_company:
            # subscription state (safe check)
            try:
                is_subscribed = user_has_active_subscription(active_company)
            except Exception:
                is_subscribed = False

            # unread notifications (use service to keep logic in one place)
            try:
                unread = unread_count(active_company, user)  # type: ignore[arg-type]
            except Exception:
                unread = 0

    return {
        "active_company": active_company,
        "is_subscribed": is_subscribed,
        "unread_notifications_count": unread,
    }


# -------------------------------------------------------------------
# Primary, recommended context processors
# -------------------------------------------------------------------

def active_company(request: HttpRequest) -> Dict[str, Any]:
    """
    Lightweight: only inject active_company.
    Prefer using app_frame() for most pages to avoid duplicate queries elsewhere.
    """
    try:
        return {"active_company": get_active_company(request)}
    except Exception:
        return {"active_company": None}


def app_frame(request: HttpRequest) -> Dict[str, Any]:
    """
    Canonical context for most app pages: active company, subscription state, and unread notifications.
    """
    return _compute_app_frame(request)


def app_globals(_request: HttpRequest) -> Dict[str, Any]:
    """
    Global branding/config values. Keep defaults stable to avoid template breakage.
    """
    return {
        "APP_NAME": getattr(settings, "APP_NAME", "EZ360PM"),
        "company_name": getattr(settings, "COMPANY_NAME", "EZ360PM, LLC"),
        "support_email": getattr(settings, "SUPPORT_EMAIL", "support@example.com"),
        "do_not_sell_url": getattr(settings, "DO_NOT_SELL_URL", ""),
        # Cookie/analytics helpers
        "COOKIE_CONSENT_NAME": getattr(settings, "COOKIE_CONSENT_NAME", "cookie_consent"),
        "PLAUSIBLE_DOMAIN": getattr(settings, "PLAUSIBLE_DOMAIN", ""),
        "GA_MEASUREMENT_ID": getattr(settings, "GA_MEASUREMENT_ID", ""),
    }


# -------------------------------------------------------------------
# Legacy / compatibility shims
# (kept to avoid breaking existing templates; all use the central helper)
# -------------------------------------------------------------------

def notifications(request: HttpRequest) -> Dict[str, Any]:
    """
    Legacy: returns only unread_notifications_count.
    Prefer app_frame().
    """
    if not getattr(getattr(request, "user", None), "is_authenticated", False):
        return {"unread_notifications_count": 0}
    ctx = _compute_app_frame(request)
    return {"unread_notifications_count": ctx["unread_notifications_count"]}


def branding(_request: HttpRequest) -> Dict[str, Any]:
    """
    Legacy: returns only APP_NAME.
    Prefer app_globals().
    """
    return {"APP_NAME": getattr(settings, "APP_NAME", "EZ360PM")}


def active_and_notifications(request: HttpRequest) -> Dict[str, Any]:
    """
    Legacy: returns active_company and unread_notifications_count.
    Prefer app_frame().
    """
    ctx = _compute_app_frame(request)
    return {
        "active_company": ctx["active_company"],
        "unread_notifications_count": ctx["unread_notifications_count"],
    }


def app_context(request: HttpRequest) -> Dict[str, Any]:
    """
    Legacy: returns active_company and is_subscribed.
    Prefer app_frame().
    """
    ctx = _compute_app_frame(request)
    return {
        "active_company": ctx["active_company"],
        "is_subscribed": ctx["is_subscribed"],
    }
