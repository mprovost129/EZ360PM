from __future__ import annotations

import os

from .base import *  # noqa

# --------------------------------------------------------------------------------------
# Production settings
# --------------------------------------------------------------------------------------

DEBUG = False

# Re-apply derived defaults that depend on DEBUG.
apply_runtime_defaults()

# In production you SHOULD set ALLOWED_HOSTS (and CSRF_TRUSTED_ORIGINS) via env.
# Example:
#   ALLOWED_HOSTS=ez360pm.com,www.ez360pm.com
#   CSRF_TRUSTED_ORIGINS=https://ez360pm.com,https://www.ez360pm.com

# If behind a proxy/load balancer
USE_X_FORWARDED_HOST = _getenv_bool("USE_X_FORWARDED_HOST", True)

# Trust X-Forwarded-Proto from proxy (common on Render/ELB)
if _getenv_bool("TRUST_X_FORWARDED_PROTO", True):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Email: default to SMTP in prod (set EMAIL_HOST etc in env)
EMAIL_BACKEND = _getenv(
    "EMAIL_BACKEND",
    "django.core.mail.backends.smtp.EmailBackend",
)


# --------------------------------------------------------------------------------------
# Logging (prod-friendly)
# --------------------------------------------------------------------------------------

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


# --------------------------------------------------------------------------------------
# Monitoring / Observability (optional)
# --------------------------------------------------------------------------------------

init_sentry_if_configured()
