from __future__ import annotations

from .base import *  # noqa
from dotenv import load_dotenv

import os

def _getenv(key, default=None):
    return os.environ.get(key, default)

load_dotenv(BASE_DIR / ".env")

DEBUG = True
# Development security settings
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = False
SECURE_HSTS_PRELOAD = False

# Sensible local defaults
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

