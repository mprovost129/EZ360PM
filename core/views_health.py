from __future__ import annotations

import time
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.http import HttpRequest, JsonResponse


def _utc_now_iso() -> str:
    return datetime.now(dt_timezone.utc).isoformat()


def _db_check() -> tuple[str, str | None]:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
            cur.fetchone()
        return "ok", None
    except Exception as e:
        return "error", str(e)[:500]


def _cache_check() -> tuple[str, str | None]:
    try:
        key = "ez360pm:health:cache"
        cache.set(key, "1", timeout=10)
        v = cache.get(key)
        if v != "1":
            return "degraded", "cache_set_get_mismatch"
        return "ok", None
    except Exception as e:
        return "error", str(e)[:500]


def _s3_check() -> tuple[str, str | None]:
    """Best-effort S3 connectivity check.

    We treat S3 as "not configured" when the app is not using S3 storage.
    """

    try:
        bucket = (getattr(settings, "AWS_STORAGE_BUCKET_NAME", "") or "").strip()
        default_storage = str(getattr(settings, "DEFAULT_FILE_STORAGE", "") or "")
        use_s3 = bool(bucket) and ("S3" in default_storage or bool(getattr(settings, "USE_S3", False)))
        if not use_s3:
            return "degraded", "s3_not_configured"

        try:
            import boto3  # type: ignore
        except Exception:
            return "error", "boto3_not_installed"

        region = (getattr(settings, "AWS_S3_REGION_NAME", "") or "").strip() or None
        client = boto3.client("s3", region_name=region)

        # Fast + low-cost check.
        client.head_bucket(Bucket=bucket)
        return "ok", None
    except Exception as e:
        return "error", str(e)[:500]


def _stripe_check() -> tuple[str, str | None]:
    try:
        sk = (getattr(settings, "STRIPE_SECRET_KEY", "") or "").strip()
        if not sk:
            return "degraded", "stripe_not_configured"

        try:
            import stripe  # type: ignore
        except Exception:
            return "error", "stripe_sdk_not_installed"

        stripe.api_key = sk
        # Lightweight auth ping. Keep timeout tight.
        stripe.Balance.retrieve(timeout=2)
        return "ok", None
    except Exception as e:
        return "error", str(e)[:500]


def _aggregate_status(parts: dict[str, str]) -> str:
    # error > degraded > ok
    if any(v == "error" for v in parts.values()):
        return "error"
    if any(v == "degraded" for v in parts.values()):
        return "degraded"
    return "ok"


def health(request: HttpRequest) -> JsonResponse:
    """Production-grade platform health endpoint.

    Designed for Render health checks + UptimeRobot.
    - Returns 200 when status=ok
    - Returns 503 when status=degraded|error

    NOTE: We do not require HEALTHCHECK_TOKEN here; it is safe and non-secret.
    """

    start = time.monotonic()

    db_s, _ = _db_check()
    cache_s, _ = _cache_check()
    s3_s, _ = _s3_check()
    stripe_s, _ = _stripe_check()

    parts = {
        "database": db_s,
        "storage_s3": s3_s,
        "stripe": stripe_s,
        "cache": cache_s,
    }

    status = _aggregate_status(parts)

    payload = {
        "status": status,
        **parts,
        "timestamp": _utc_now_iso(),
        "latency_ms": int((time.monotonic() - start) * 1000),
        "version": getattr(settings, "BUILD_VERSION", "")
        or getattr(settings, "RELEASE_SHA", "")
        or "",
    }

    http_status = 200 if status == "ok" else 503
    return JsonResponse(payload, status=http_status)


def health_details(request: HttpRequest) -> JsonResponse:
    """Token-protected detailed healthcheck.

    Requires settings.HEALTHCHECK_TOKEN. If not set, returns 404.
    Token can be provided via:
      - Header: X-Health-Token
      - Query:  ?token=...

    Includes best-effort error summaries per component.
    """

    token = (getattr(settings, "HEALTHCHECK_TOKEN", "") or "").strip()
    if not token:
        return JsonResponse({"detail": "not found"}, status=404)

    supplied = (request.headers.get("X-Health-Token") or request.GET.get("token") or "").strip()
    if supplied != token:
        return JsonResponse({"detail": "unauthorized"}, status=401)

    start = time.monotonic()

    db_s, db_err = _db_check()
    cache_s, cache_err = _cache_check()
    s3_s, s3_err = _s3_check()
    stripe_s, stripe_err = _stripe_check()

    parts = {
        "database": db_s,
        "storage_s3": s3_s,
        "stripe": stripe_s,
        "cache": cache_s,
    }

    status = _aggregate_status(parts)

    payload = {
        "status": status,
        **parts,
        "errors": {
            "database": db_err,
            "storage_s3": s3_err,
            "stripe": stripe_err,
            "cache": cache_err,
        },
        "timestamp": _utc_now_iso(),
        "latency_ms": int((time.monotonic() - start) * 1000),
        "environment": getattr(settings, "ENVIRONMENT", ""),
        "app_environment": getattr(settings, "APP_ENVIRONMENT", ""),
        "release_sha": getattr(settings, "RELEASE_SHA", "") or getattr(settings, "BUILD_SHA", ""),
    }

    http_status = 200 if status == "ok" else 503
    return JsonResponse(payload, status=http_status)
