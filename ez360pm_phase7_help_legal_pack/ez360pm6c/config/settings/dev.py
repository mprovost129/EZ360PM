from __future__ import annotations

from .base import *  # noqa
import os

def _getenv(key, default=None):
    return os.environ.get(key, default)

def _getenv_bool(key, default=False):
    val = os.environ.get(key, None)
    if val is None:
        return default
    return val.strip().lower() not in {"0", "false", "no"}

# --------------------------------------------------------------------------------------
# Development settings
# --------------------------------------------------------------------------------------

DEBUG = True

# Re-apply derived defaults that depend on DEBUG.
apply_runtime_defaults()

# Local-only safe hosts
if not ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["127.0.0.1", "localhost"]

# Development conveniences
EMAIL_BACKEND = _getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)

# Relax cookies locally
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# -----------------------------------------------------------------------------
# Dev HTTP/HTTPS behavior
# -----------------------------------------------------------------------------
# In development, we must remain reachable over plain HTTP by default.
# If you want to test HTTPS locally, set:
#   DEV_SECURE_SSL_REDIRECT=1
# and run an HTTPS-capable dev server (e.g. via Caddy/nginx/traefik or runserver_plus).
SECURE_SSL_REDIRECT = _getenv_bool("DEV_SECURE_SSL_REDIRECT", False)

# --------------------------------------------------------------------------------------
# Phase 3W: Lightweight performance logging (dev only)
# --------------------------------------------------------------------------------------
# Logs slow requests and slow ORM queries.
# Requires DEBUG=True for connection.queries timing.
EZ360_PERF_LOGGING_ENABLED = (
    _getenv("EZ360_PERF_LOGGING_ENABLED", "1").strip().lower() not in {"0", "false", "no"}
)
EZ360_PERF_REQUEST_MS = int(_getenv("EZ360_PERF_REQUEST_MS", "600"))
EZ360_PERF_QUERY_MS = int(_getenv("EZ360_PERF_QUERY_MS", "120"))
EZ360_PERF_TOP_N = int(_getenv("EZ360_PERF_TOP_N", "5"))
EZ360_PERF_SAMPLE_RATE = float(_getenv("EZ360_PERF_SAMPLE_RATE", "1.0"))
EZ360_PERF_STORE_DB = _getenv_bool("EZ360_PERF_STORE_DB", False)

# Insert perf middleware early so it captures the full request.
_mw = list(MIDDLEWARE)
if "core.middleware.PerformanceLoggingMiddleware" not in _mw:
    if "django.middleware.common.CommonMiddleware" in _mw:
        idx = _mw.index("django.middleware.common.CommonMiddleware") + 1
    else:
        idx = 0
    _mw.insert(idx, "core.middleware.PerformanceLoggingMiddleware")
MIDDLEWARE = _mw

# Always allow local hosts in development
ALLOWED_HOSTS = ["127.0.0.1", "localhost"]


# Optional monitoring in dev (only if SENTRY_DSN is set)
init_sentry_if_configured()


# Backups (dev defaults)
BACKUP_ENABLED = _getenv_bool("DEV_BACKUP_ENABLED", False)
