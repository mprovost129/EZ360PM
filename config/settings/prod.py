from __future__ import annotations

import os

from .base import *  # noqa


def _getenv(key, default=None):
    return os.environ.get(key, default)


def _getenv_bool(key, default=False):
    val = os.environ.get(key, None)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


DEBUG = False

# Re-apply derived defaults that depend on DEBUG.
apply_runtime_defaults()

# If behind a proxy/load balancer
USE_X_FORWARDED_HOST = _getenv_bool("USE_X_FORWARDED_HOST", True)

# Trust X-Forwarded-Proto from proxy (common on Render/ELB)
if _getenv_bool("TRUST_X_FORWARDED_PROTO", True):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

EMAIL_BACKEND = _getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)

# Optional perf logging
EZ360_PERF_LOGGING_ENABLED = _getenv_bool("EZ360_PERF_LOGGING_ENABLED", False)
EZ360_PERF_REQUEST_MS = int(_getenv("EZ360_PERF_REQUEST_MS", "800"))
EZ360_PERF_QUERY_MS = int(_getenv("EZ360_PERF_QUERY_MS", "200"))
EZ360_PERF_TOP_N = int(_getenv("EZ360_PERF_TOP_N", "3"))
EZ360_PERF_SAMPLE_RATE = float(_getenv("EZ360_PERF_SAMPLE_RATE", "0.25"))
EZ360_PERF_STORE_DB = _getenv_bool("EZ360_PERF_STORE_DB", False)

if EZ360_PERF_LOGGING_ENABLED:
    _mw = list(MIDDLEWARE)
    if "core.middleware.PerformanceLoggingMiddleware" not in _mw:
        if "django.middleware.common.CommonMiddleware" in _mw:
            idx = _mw.index("django.middleware.common.CommonMiddleware") + 1
        else:
            idx = 0
        _mw.insert(idx, "core.middleware.PerformanceLoggingMiddleware")
    MIDDLEWARE = _mw

# Logging tweaks
LOGGING = LOGGING
LOGGING["loggers"].update(
    {
        "billing.webhooks": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "core.email_utils": {"handlers": ["console"], "level": "INFO", "propagate": False},
    }
)

# Monitoring
init_sentry_if_configured()
