from __future__ import annotations

from django.conf import settings
from django.db import connection
from django.http import HttpRequest, JsonResponse
from django.utils import timezone


def _db_ok() -> bool:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return True
    except Exception:
        return False


def health(request: HttpRequest) -> JsonResponse:
    """Public, safe healthcheck for uptime monitors.

    - No secrets
    - Minimal surface: process + DB connectivity
    - 200 when healthy, 503 when unhealthy
    """

    db_ok = _db_ok()
    payload = {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "down",
        "version": getattr(settings, "BUILD_VERSION", "")
        or getattr(settings, "RELEASE_SHA", "")
        or "",
    }
    return JsonResponse(payload, status=200 if db_ok else 503)


def health_details(request: HttpRequest) -> JsonResponse:
    """Token-protected healthcheck (optional deeper detail).

    Requires settings.HEALTHCHECK_TOKEN. If not set, returns 404.
    Token can be provided via:
      - Header: X-Health-Token
      - Query:  ?token=...
    """

    token = getattr(settings, "HEALTHCHECK_TOKEN", "") or ""
    if not token:
        return JsonResponse({"detail": "not found"}, status=404)

    supplied = request.headers.get("X-Health-Token") or request.GET.get("token") or ""
    if supplied != token:
        return JsonResponse({"detail": "unauthorized"}, status=401)

    db_ok = _db_ok()
    payload = {
        "status": "ok" if db_ok else "degraded",
        "db": "ok" if db_ok else "down",
        "environment": getattr(settings, "ENVIRONMENT", ""),
        "app_environment": getattr(settings, "APP_ENVIRONMENT", ""),
        "release_sha": getattr(settings, "RELEASE_SHA", "") or getattr(settings, "BUILD_SHA", ""),
        "checked_at": timezone.now().isoformat(),
    }
    return JsonResponse(payload, status=200 if db_ok else 503)
