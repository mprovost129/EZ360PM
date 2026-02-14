from __future__ import annotations

from typing import Any

from django.http import HttpRequest

from companies.models import Company, EmployeeProfile

from .models import AuditEvent


def log_event(
    *,
    company: Company,
    actor: EmployeeProfile | None,
    event_type: str,
    object_type: str,
    object_id=None,
    summary: str = "",
    payload: dict[str, Any] | None = None,
    request: HttpRequest | None = None,
) -> AuditEvent:
    """Create a per-company audit event."""
    payload = payload or {}

    ip_address = None
    user_agent = ""
    if request is not None:
        ip_address = request.META.get("REMOTE_ADDR")
        user_agent = str(request.META.get("HTTP_USER_AGENT") or "")

    return AuditEvent.objects.create(
        company=company,
        actor=actor,
        event_type=str(event_type),
        object_type=str(object_type),
        object_id=object_id,
        summary=summary or "",
        payload_json=payload,
        ip_address=ip_address,
        user_agent=user_agent,
    )
