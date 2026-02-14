from __future__ import annotations

import os

from .base import *  # noqa


def _getenv(key: str, default: str | None = None) -> str:
    return os.environ.get(key, default or "")


def _getenv_bool(key: str, default: bool = False) -> bool:
    val = os.environ.get(key, None)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


# --------------------------------------------------------------------------------------
# Development settings
# --------------------------------------------------------------------------------------

DEBUG = True

# Re-apply derived defaults that depend on DEBUG (imported from base.py)
apply_runtime_defaults()

# Local-only safe hosts/origins
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

if not CSRF_TRUSTED_ORIGINS:
    CSRF_TRUSTED_ORIGINS = ["http://127.0.0.1:8000", "http://localhost:8000"]

# Development conveniences
EMAIL_BACKEND = _getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)

# Relax cookies locally (explicit)
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# In development, stay reachable over plain HTTP by default.
# If you want to test HTTPS locally, set:
#   DEV_SECURE_SSL_REDIRECT=1
SECURE_SSL_REDIRECT = _getenv_bool("DEV_SECURE_SSL_REDIRECT", False)

# --------------------------------------------------------------------------------------
# Phase 3W: Lightweight performance logging (dev only)
# --------------------------------------------------------------------------------------
EZ360_PERF_LOGGING_ENABLED = _getenv_bool("EZ360_PERF_LOGGING_ENABLED", True)
EZ360_PERF_REQUEST_MS = int(_getenv("EZ360_PERF_REQUEST_MS", "600") or "600")
EZ360_PERF_QUERY_MS = int(_getenv("EZ360_PERF_QUERY_MS", "120") or "120")
EZ360_PERF_TOP_N = int(_getenv("EZ360_PERF_TOP_N", "5") or "5")
EZ360_PERF_SAMPLE_RATE = float(_getenv("EZ360_PERF_SAMPLE_RATE", "1.0") or "1.0")
EZ360_PERF_STORE_DB = _getenv_bool("EZ360_PERF_STORE_DB", False)

# Insert perf middleware early so it captures the full request.
if EZ360_PERF_LOGGING_ENABLED:
    _mw = list(MIDDLEWARE)
    if "core.middleware.PerformanceLoggingMiddleware" not in _mw:
        if "django.middleware.common.CommonMiddleware" in _mw:
            idx = _mw.index("django.middleware.common.CommonMiddleware") + 1
        else:
            idx = 0
        _mw.insert(idx, "core.middleware.PerformanceLoggingMiddleware")
    MIDDLEWARE = _mw

# Optional monitoring in dev (only if SENTRY_DSN is set)
init_sentry_if_configured()

# Backups (dev defaults)
BACKUP_ENABLED = _getenv_bool("DEV_BACKUP_ENABLED", False)
