from __future__ import annotations

import os
from typing import Any, Dict, List

from django.conf import settings


def _bool(v: Any) -> bool:
    return bool(v)


def _result(
    *,
    check_id: str,
    title: str,
    ok: bool,
    level: str = "error",
    message: str = "",
    hint: str = "",
) -> Dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "ok": bool(ok),
        "level": level,  # error | warn | info
        "message": message,
        "hint": hint,
    }


def run_launch_checks() -> List[Dict[str, Any]]:
    """Run a practical launch-readiness checklist.

    Intentionally lightweight: reads Django settings/env only.
    """
    out: List[Dict[str, Any]] = []

    # --- Security posture
    debug = getattr(settings, "DEBUG", False)
    out.append(
        _result(
            check_id="debug_off",
            title="DEBUG is disabled",
            ok=not debug,
            level="error",
            message="DEBUG is ON" if debug else "DEBUG is OFF",
            hint="Set DEBUG=False in production.",
        )
    )

    secret_key = getattr(settings, "SECRET_KEY", "")
    out.append(
        _result(
            check_id="secret_key_set",
            title="SECRET_KEY is configured",
            ok=_bool(secret_key) and "django-insecure" not in str(secret_key),
            level="error",
            message="SECRET_KEY looks insecure" if ("django-insecure" in str(secret_key)) else "SECRET_KEY configured",
            hint="Use a strong random SECRET_KEY in production.",
        )
    )

    allowed_hosts = getattr(settings, "ALLOWED_HOSTS", [])
    out.append(
        _result(
            check_id="allowed_hosts",
            title="ALLOWED_HOSTS configured",
            ok=isinstance(allowed_hosts, (list, tuple)) and len(allowed_hosts) > 0 and "*" not in allowed_hosts,
            level="warn" if (allowed_hosts == ["*"] or allowed_hosts == "*") else "error",
            message=f"ALLOWED_HOSTS={allowed_hosts}",
            hint="Set explicit hosts (no '*') for production.",
        )
    )

    secure_redirect = getattr(settings, "SECURE_SSL_REDIRECT", False)
    out.append(
        _result(
            check_id="ssl_redirect",
            title="HTTPS redirect enabled",
            ok=bool(secure_redirect) or debug,
            level="warn",
            message="SECURE_SSL_REDIRECT is ON" if secure_redirect else "SECURE_SSL_REDIRECT is OFF",
            hint="Set SECURE_SSL_REDIRECT=True in production behind TLS.",
        )
    )

    # --- Secure cookies + HSTS (recommended for production)
    session_secure = getattr(settings, "SESSION_COOKIE_SECURE", False)
    csrf_secure = getattr(settings, "CSRF_COOKIE_SECURE", False)
    out.append(
        _result(
            check_id="secure_cookies",
            title="Secure cookies enabled",
            ok=debug or (bool(session_secure) and bool(csrf_secure)),
            level="warn",
            message=f"SESSION_COOKIE_SECURE={session_secure} CSRF_COOKIE_SECURE={csrf_secure}",
            hint="Set SESSION_COOKIE_SECURE=True and CSRF_COOKIE_SECURE=True in production.",
        )
    )

    hsts_seconds = getattr(settings, "SECURE_HSTS_SECONDS", 0)
    out.append(
        _result(
            check_id="hsts",
            title="HSTS configured",
            ok=debug or int(hsts_seconds) >= 3600,
            level="warn",
            message=f"SECURE_HSTS_SECONDS={hsts_seconds}",
            hint="Set SECURE_HSTS_SECONDS>=3600 in production once HTTPS is stable.",
        )
    )

    # --- Stripe
    stripe_secret = os.environ.get("STRIPE_SECRET_KEY") or getattr(settings, "STRIPE_SECRET_KEY", None)
    stripe_webhook = os.environ.get("STRIPE_WEBHOOK_SECRET") or getattr(settings, "STRIPE_WEBHOOK_SECRET", None)
    out.append(
        _result(
            check_id="stripe_secret_key",
            title="Stripe secret key configured",
            ok=_bool(stripe_secret),
            level="error",
            message="Configured" if stripe_secret else "Missing STRIPE_SECRET_KEY",
            hint="Set STRIPE_SECRET_KEY in env.",
        )
    )
    out.append(
        _result(
            check_id="stripe_webhook_secret",
            title="Stripe webhook secret configured",
            ok=_bool(stripe_webhook),
            level="warn",
            message="Configured" if stripe_webhook else "Missing STRIPE_WEBHOOK_SECRET",
            hint="Set STRIPE_WEBHOOK_SECRET for signature verification.",
        )
    )

    # --- Email
    email_backend = getattr(settings, "EMAIL_BACKEND", "")
    out.append(
        _result(
            check_id="email_backend",
            title="Email backend configured",
            ok=_bool(email_backend) and "console" not in str(email_backend).lower(),
            level="warn",
            message=f"EMAIL_BACKEND={email_backend}",
            hint="Use SMTP/transactional email backend in production.",
        )
    )

    # --- Static/media
    static_root = getattr(settings, "STATIC_ROOT", "")
    out.append(
        _result(
            check_id="static_root",
            title="STATIC_ROOT configured",
            ok=_bool(static_root),
            level="warn",
            message=f"STATIC_ROOT={static_root}",
            hint="Set STATIC_ROOT and run collectstatic for production.",
        )
    )

    # --- Sentry (optional)
    sentry_dsn = os.environ.get("SENTRY_DSN") or getattr(settings, "SENTRY_DSN", None)
    out.append(
        _result(
            check_id="sentry_dsn",
            title="Sentry configured (optional)",
            ok=_bool(sentry_dsn) or debug,
            level="info",
            message="Configured" if sentry_dsn else "Not configured",
            hint="Set SENTRY_DSN if you want error tracking.",
        )
    )

    # --- Build metadata (helps debugging prod incidents)
    build_sha = getattr(settings, "BUILD_SHA", "")
    build_ver = getattr(settings, "BUILD_VERSION", "")
    if not debug:
        out.append(
            _result(
                check_id="build_metadata",
                title="Build metadata configured (version/sha)",
                ok=_bool(build_sha) or _bool(build_ver),
                level="warn",
                message=f"BUILD_VERSION={build_ver or '(blank)'} BUILD_SHA={build_sha or '(blank)'}",
                hint="Set BUILD_SHA (git SHA) and optionally BUILD_VERSION in your deploy pipeline for better incident triage.",
            )
        )


    # --- Backup/restore evidence (process gate)
    try:
        from ops.models import BackupRestoreTest, RestoreTestOutcome  # type: ignore
        latest = BackupRestoreTest.objects.first()
        ok = bool(latest and latest.outcome == RestoreTestOutcome.PASS)
        msg = "No restore test recorded"
        if latest:
            msg = f"Latest: {latest.tested_at:%Y-%m-%d} ({latest.outcome})"
        out.append(
            _result(
                check_id="backup_restore_test_recent",
                title="Backup restore test recorded (latest is PASS)",
                ok=ok,
                level="warn" if not ok else "info",
                message=msg,
                hint="Perform a restore test (managed Postgres restore or snapshot restore) and record it in Ops → Backups.",
            )
        )
    except Exception:
        # If ops app isn't available during early setup, don't block.
        out.append(
            _result(
                check_id="backup_restore_test_recent",
                title="Backup restore test recorded (latest is PASS)",
                ok=False,
                level="warn",
                message="Unable to load ops backup restore test model",
                hint="Ensure ops app is installed and database is migrated.",
            )
        )

    return out
