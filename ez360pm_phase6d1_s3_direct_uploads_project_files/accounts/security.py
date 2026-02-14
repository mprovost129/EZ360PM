from __future__ import annotations

from typing import Optional

from django.http import HttpRequest

from .models import LoginEvent, User


def _get_client_ip(request: HttpRequest) -> str:
    # Prefer X-Forwarded-For if behind a proxy (take first IP).
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()[:64]
    return (request.META.get("REMOTE_ADDR") or "")[:64]


def _get_user_agent(request: HttpRequest) -> str:
    return (request.META.get("HTTP_USER_AGENT") or "")[:255]


def log_login_success(request: HttpRequest, user: User, *, method: str) -> None:
    """Record a successful authentication event for the user's security history."""
    LoginEvent.objects.create(
        user=user,
        method=method,
        ip_address=_get_client_ip(request),
        user_agent=_get_user_agent(request),
    )
