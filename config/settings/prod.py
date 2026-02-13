from __future__ import annotations

from .base import *  # noqa
from dotenv import load_dotenv

import os

def _getenv(key, default=None):
    return os.environ.get(key, default)

def _getenv_bool(key, default=False):
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() in ("1", "true", "yes", "on")

def _getenv_int(key, default=0):
    val = os.environ.get(key)
    if val is None:
        return default
    try:
        return int(val)
    except ValueError:
        return default

load_dotenv(BASE_DIR / ".env")

DEBUG = False

# In production you MUST set ALLOWED_HOSTS (and CSRF_TRUSTED_ORIGINS) via env.
# Example:
#   ALLOWED_HOSTS=ez360pm.com,www.ez360pm.com
#   CSRF_TRUSTED_ORIGINS=https://ez360pm.com,https://www.ez360pm.com

# Security
SECURE_SSL_REDIRECT = _getenv_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = _getenv_bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = _getenv_bool("CSRF_COOKIE_SECURE", True)

SECURE_HSTS_SECONDS = _getenv_int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _getenv_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = _getenv_bool("SECURE_HSTS_PRELOAD", False)

SECURE_REFERRER_POLICY = _getenv("SECURE_REFERRER_POLICY", "same-origin")

# If behind a proxy/load balancer
USE_X_FORWARDED_HOST = _getenv_bool("USE_X_FORWARDED_HOST", True)

# Trust X-Forwarded-Proto from proxy (common on Render/ELB)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
# Production security settings
SECURE_SSL_REDIRECT = _getenv_bool("SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = _getenv_bool("SESSION_COOKIE_SECURE", True)
CSRF_COOKIE_SECURE = _getenv_bool("CSRF_COOKIE_SECURE", True)
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = _getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = _getenv("CSRF_COOKIE_SAMESITE", "Lax")
SECURE_HSTS_SECONDS = _getenv_int("SECURE_HSTS_SECONDS", 60 * 60 * 24 * 30)
SECURE_HSTS_INCLUDE_SUBDOMAINS = _getenv_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", True)
SECURE_HSTS_PRELOAD = _getenv_bool("SECURE_HSTS_PRELOAD", False)


# Email: default to SMTP in prod (set EMAIL_HOST etc in env)
EMAIL_BACKEND = _getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)



# -----------------------------------------------------------------------------
# Logging (prod-friendly)
# -----------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {"format": "%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s"},
    },
    "filters": {
        "request_id": {
            "()": "core.logging_filters.RequestIDFilter",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": "INFO"},
}


# -------------------------
# Monitoring / Observability
# -------------------------
SENTRY_DSN = os.getenv("SENTRY_DSN", "")
SENTRY_ENVIRONMENT = os.getenv("SENTRY_ENVIRONMENT", ENVIRONMENT)
SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05") or "0.05")
SENTRY_PROFILES_SAMPLE_RATE = float(os.getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0") or "0.0")

if SENTRY_DSN:
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=SENTRY_DSN,
            environment=SENTRY_ENVIRONMENT,
            release=RELEASE_SHA or None,
            integrations=[DjangoIntegration()],
            traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
            profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
            send_default_pii=False,
        )
    except Exception:
        # Fail closed: app must still boot without sentry installed.
        pass


LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
        }
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "standard"},
    },
    "root": {"handlers": ["console"], "level": os.getenv("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "billing.webhooks": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "core.email_utils": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}
