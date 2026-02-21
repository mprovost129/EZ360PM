from __future__ import annotations

from functools import wraps

from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from accounts.models import AccountLockout

from .models import OpsAlertEvent, OpsAlertSource


def _is_staff(user) -> bool:
    return bool(user and user.is_authenticated and user.is_staff)


def staff_only(view_func):
    """Decorator: staff-only view (login required)."""

    @login_required
    @user_passes_test(_is_staff)
    @wraps(view_func)
    def _wrapped(request: HttpRequest, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return _wrapped


@staff_only
def ops_security(request: HttpRequest) -> HttpResponse:
    """Ops Security dashboard.

    Shows recent account lockouts and unresolved auth/throttle alerts.
    This view is intentionally lightweight and does not call external services.
    """

    lockouts = AccountLockout.objects.all().order_by("-updated_at")[:50]

    auth_alerts = (
        OpsAlertEvent.objects.select_related("company")
        .filter(source=OpsAlertSource.AUTH, is_resolved=False)
        .order_by("-created_at")[:25]
    )
    throttle_alerts = (
        OpsAlertEvent.objects.select_related("company")
        .filter(source=OpsAlertSource.THROTTLE, is_resolved=False)
        .order_by("-created_at")[:25]
    )

    counts = {
        "open_auth": OpsAlertEvent.objects.filter(source=OpsAlertSource.AUTH, is_resolved=False).count(),
        "open_throttle": OpsAlertEvent.objects.filter(source=OpsAlertSource.THROTTLE, is_resolved=False).count(),
    }

    return render(
        request,
        "ops/security.html",
        {
            "counts": counts,
            "lockouts": lockouts,
            "auth_alerts": auth_alerts,
            "throttle_alerts": throttle_alerts,
        },
    )
