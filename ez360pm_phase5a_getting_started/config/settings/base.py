from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

# Base directory (project root)
BASE_DIR = Path(__file__).resolve().parents[2]

# Load environment variables from .env (if present)
load_dotenv(BASE_DIR / ".env")


def _getenv(name: str, default: str | None = None) -> str:
    val = os.getenv(name)
    if val is None:
        return "" if default is None else default
    return str(val)


def _getenv_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on"}


def _getenv_int(name: str, default: int = 0) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


# --------------------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------------------

# Debug defaults to OFF here. dev.py / prod.py own the authoritative toggle.
DEBUG = _getenv_bool("DEBUG", False)

SECRET_KEY = _getenv("SECRET_KEY", "django-insecure-CHANGE_ME")

# Hosts / origins (prod should set these via env; dev.py provides safe local defaults)
ALLOWED_HOSTS = [h.strip() for h in _getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]


INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",

    # Third-party
    "rest_framework",
    "rest_framework_simplejwt",

    # Project apps
    "accounts",
    "audit",
    "accounting",
    "billing",
    "catalog",
    "companies",
    "core",
    "crm",
    "documents",
    "expenses",
    "payments",
    "projects",
    "integrations",
    "sync",
    "timetracking",
    "ops",
]


AUTH_USER_MODEL = "accounts.User"


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.RequestIDMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",

    # Support mode (staff-only, time-limited)
    "core.middleware.SupportModeMiddleware",
    "core.middleware.SupportModeReadOnlyMiddleware",

    # Hardening gates
    "core.middleware.EmailVerificationGateMiddleware",
    "core.middleware.TwoFactorEnforcementMiddleware",
    "core.middleware.SubscriptionLockMiddleware",

    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.SecurityHeadersMiddleware",
]


ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.app_context",
            ],
        },
    }
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"


# --------------------------------------------------------------------------------------
# Database
# --------------------------------------------------------------------------------------

# Supports either:
# - DATABASE_URL (recommended, future)
# - or individual POSTGRES_* vars
# - or legacy NAME/USER/PASSWORD/HOST/PORT vars
DATABASE_URL = _getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # Placeholder: if you later add dj-database-url, switch here.
    pass

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _getenv("POSTGRES_DB", _getenv("NAME", "ez360pm")),
        "USER": _getenv("POSTGRES_USER", _getenv("USER", "ez360pmuser")),
        "PASSWORD": _getenv("POSTGRES_PASSWORD", _getenv("PASSWORD", "")),
        "HOST": _getenv("POSTGRES_HOST", _getenv("HOST", "localhost")),
        "PORT": _getenv("POSTGRES_PORT", _getenv("PORT", "5432")),
        "CONN_MAX_AGE": _getenv_int("DB_CONN_MAX_AGE", 0),
    }
}


# --------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------

EZ360_CACHE_ENABLED = _getenv_bool("EZ360_CACHE_ENABLED", False)
REDIS_URL = _getenv("REDIS_URL", "").strip()

if REDIS_URL:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": REDIS_URL,
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ez360pm",
        }
    }


# --------------------------------------------------------------------------------------
# Password validation
# --------------------------------------------------------------------------------------

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# --------------------------------------------------------------------------------------
# Internationalization
# --------------------------------------------------------------------------------------

LANGUAGE_CODE = "en-us"
TIME_ZONE = _getenv("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# --------------------------------------------------------------------------------------
# Static & media
# --------------------------------------------------------------------------------------

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# --------------------------------------------------------------------------------------
# DRF
# --------------------------------------------------------------------------------------

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}


# --------------------------------------------------------------------------------------
# App constants
# --------------------------------------------------------------------------------------

EZ360PM_TRIAL_DAYS = _getenv_int("EZ360PM_TRIAL_DAYS", 14)

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"

SITE_NAME = _getenv("SITE_NAME", "EZ360PM")


# --------------------------------------------------------------------------------------
# Email
# --------------------------------------------------------------------------------------

EMAIL_HOST = _getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = _getenv_int("EMAIL_PORT", 587)
EMAIL_USE_TLS = _getenv_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = _getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _getenv("EMAIL_HOST_PASSWORD", "")

DEFAULT_FROM_EMAIL = _getenv("DEFAULT_FROM_EMAIL", "info@ez360pm.com")
SERVER_EMAIL = _getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

SUPPORT_EMAIL = _getenv("SUPPORT_EMAIL", "support@ez360pm.com")
DEFAULT_REPLY_TO_EMAIL = _getenv("DEFAULT_REPLY_TO_EMAIL", SUPPORT_EMAIL).strip()
EMAIL_SUBJECT_PREFIX = _getenv("EMAIL_SUBJECT_PREFIX", "[EZ360PM] ")


# --------------------------------------------------------------------------------------
# Stripe (Subscriptions)
# --------------------------------------------------------------------------------------

STRIPE_SECRET_KEY = _getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = _getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = _getenv("STRIPE_WEBHOOK_SECRET", "")
STRIPE_PORTAL_CONFIGURATION_ID = _getenv("STRIPE_PORTAL_CONFIGURATION_ID", "")

_raw_price_map = _getenv("STRIPE_PRICE_MAP_JSON", "")
STRIPE_PRICE_MAP: dict[str, str] = {}
if _raw_price_map:
    try:
        loaded = json.loads(_raw_price_map)
        if isinstance(loaded, dict):
            STRIPE_PRICE_MAP = loaded
    except Exception:
        STRIPE_PRICE_MAP = {}


# --------------------------------------------------------------------------------------
# Security / hardening knobs (derived defaults applied via apply_runtime_defaults)
# --------------------------------------------------------------------------------------

# If behind a proxy/load balancer (Render/ELB)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Two-factor auth (TOTP)
TWO_FACTOR_ISSUER = _getenv("TWO_FACTOR_ISSUER", "EZ360PM")


# reCAPTCHA v3
RECAPTCHA_ENABLED = os.getenv("RECAPTCHA_ENABLED", "0") == "1"
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY", "")
RECAPTCHA_MIN_SCORE = float(os.getenv("RECAPTCHA_MIN_SCORE", "0.5"))


# Dropbox Integration (Pack U)
DROPBOX_APP_KEY = _getenv("DROPBOX_APP_KEY", "").strip()
DROPBOX_APP_SECRET = _getenv("DROPBOX_APP_SECRET", "").strip()
DROPBOX_REDIRECT_URI = _getenv("DROPBOX_REDIRECT_URI", "").strip()


# Backups
EZ360_BACKUP_DIR = Path(_getenv("EZ360_BACKUP_DIR", str(BASE_DIR / "backups")))
EZ360_BACKUP_RETENTION_DAYS = _getenv_int("EZ360_BACKUP_RETENTION_DAYS", 14)
EZ360_BACKUP_KEEP_LAST = _getenv_int("EZ360_BACKUP_KEEP_LAST", 14)


ENVIRONMENT = os.getenv("EZ360_ENV", "dev")
RELEASE_SHA = os.getenv("EZ360_RELEASE_SHA", "")


# Ops retention / pruning
EZ360_AUDIT_RETENTION_DAYS = _getenv_int("EZ360_AUDIT_RETENTION_DAYS", 365)
EZ360_STRIPE_WEBHOOK_RETENTION_DAYS = _getenv_int("EZ360_STRIPE_WEBHOOK_RETENTION_DAYS", 90)


# --------------------------------------------------------------------------------------
# Derived defaults (must be re-run by dev.py/prod.py after overriding DEBUG)
# --------------------------------------------------------------------------------------

def apply_runtime_defaults() -> None:
    """Apply settings that depend on DEBUG and/or are env-tunable.

    IMPORTANT:
    - base.py defines safe defaults.
    - dev.py/prod.py may override DEBUG and then re-run this to keep dependent defaults correct.
    """
    global ACCOUNTS_REQUIRE_EMAIL_VERIFICATION
    global ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS
    global SECURE_SSL_REDIRECT, SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE
    global SESSION_COOKIE_HTTPONLY, CSRF_COOKIE_HTTPONLY
    global SESSION_COOKIE_SAMESITE, CSRF_COOKIE_SAMESITE
    global SECURE_HSTS_SECONDS, SECURE_HSTS_INCLUDE_SUBDOMAINS, SECURE_HSTS_PRELOAD
    global EZ360_CSP_ENABLED, SECURE_CSP_REPORT_ONLY, SECURE_CSP
    global COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS
    global SLOW_REQUEST_THRESHOLD_MS
    global EZ360_ALERT_ON_WEBHOOK_FAILURE, EZ360_ALERT_ON_EMAIL_FAILURE
    global ADMINS

    # ---- Accounts / Verification ----
    _require_verify_env = os.getenv("ACCOUNTS_REQUIRE_EMAIL_VERIFICATION", "").strip()
    if _require_verify_env in {"0", "1"}:
        ACCOUNTS_REQUIRE_EMAIL_VERIFICATION = _require_verify_env == "1"
    else:
        ACCOUNTS_REQUIRE_EMAIL_VERIFICATION = not DEBUG

    ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS = int(
        os.getenv("ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS", str(60 * 60 * 24 * 3))
    )

    # ---- Security hardening defaults ----
    _secure_default = not DEBUG
    SECURE_SSL_REDIRECT = _getenv_bool("SECURE_SSL_REDIRECT", _secure_default)
    SESSION_COOKIE_SECURE = _getenv_bool("SESSION_COOKIE_SECURE", _secure_default)
    CSRF_COOKIE_SECURE = _getenv_bool("CSRF_COOKIE_SECURE", _secure_default)

    SESSION_COOKIE_HTTPONLY = True
    CSRF_COOKIE_HTTPONLY = False

    SESSION_COOKIE_SAMESITE = _getenv("SESSION_COOKIE_SAMESITE", "Lax")
    CSRF_COOKIE_SAMESITE = _getenv("CSRF_COOKIE_SAMESITE", "Lax")

    SECURE_HSTS_SECONDS = _getenv_int("SECURE_HSTS_SECONDS", 31536000 if _secure_default else 0)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False

    # ---- CSP rollout ----
    EZ360_CSP_ENABLED = _getenv_bool("EZ360_CSP_ENABLED", not DEBUG)
    SECURE_CSP_REPORT_ONLY = {
        "default-src": ["'self'"],
        "img-src": ["'self'", "data:"],
        "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "font-src": ["'self'", "data:", "https://cdn.jsdelivr.net"],
        "connect-src": ["'self'"],
        "frame-ancestors": ["'none'"]
    }

    if EZ360_CSP_ENABLED:
        SECURE_CSP = {
            "default-src": ["'self'"],
            "img-src": ["'self'", "data:"],
            "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
            "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
            "font-src": ["'self'", "data:", "https://cdn.jsdelivr.net"],
            "connect-src": ["'self'"],
            "frame-ancestors": ["'none'"],
        }
    else:
        SECURE_CSP = ""

    # ---- Company security defaults ----
    _default_company_2fa_env = os.getenv("COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS", "").strip()
    if _default_company_2fa_env in {"0", "1"}:
        COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS = _default_company_2fa_env == "1"
    else:
        COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS = not DEBUG

    SLOW_REQUEST_THRESHOLD_MS = int(os.getenv("EZ360_SLOW_REQUEST_MS", "1500"))

    # ---- Ops alerts ----
    _alert_webhook_env = _getenv("EZ360_ALERT_ON_WEBHOOK_FAILURE", "").strip()
    if _alert_webhook_env in {"0", "1"}:
        EZ360_ALERT_ON_WEBHOOK_FAILURE = _alert_webhook_env == "1"
    else:
        EZ360_ALERT_ON_WEBHOOK_FAILURE = not DEBUG

    _alert_email_env = _getenv("EZ360_ALERT_ON_EMAIL_FAILURE", "").strip()
    if _alert_email_env in {"0", "1"}:
        EZ360_ALERT_ON_EMAIL_FAILURE = _alert_email_env == "1"
    else:
        EZ360_ALERT_ON_EMAIL_FAILURE = not DEBUG

    # Optional: "Name:email,Name2:email2".
    _raw_admins = _getenv("EZ360_ADMINS", "").strip()
    ADMINS = []
    if _raw_admins:
        for part in _raw_admins.split(","):
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                name, email = part.split(":", 1)
                name = name.strip() or "Admin"
                email = email.strip()
            else:
                name, email = "Admin", part.strip()
            if email:
                ADMINS.append((name, email))




def init_sentry_if_configured() -> None:
    """Initialize Sentry if SENTRY_DSN is set.

    Safe to call in any environment; if sentry-sdk isn't installed, app still boots.
    """
    dsn = _getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return

    environment = _getenv("SENTRY_ENVIRONMENT", ENVIRONMENT).strip() or ENVIRONMENT
    try:
        traces = float(_getenv("SENTRY_TRACES_SAMPLE_RATE", "0.05") or "0.05")
    except Exception:
        traces = 0.05
    try:
        profiles = float(_getenv("SENTRY_PROFILES_SAMPLE_RATE", "0.0") or "0.0")
    except Exception:
        profiles = 0.0

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=RELEASE_SHA or None,
            integrations=[DjangoIntegration()],
            traces_sample_rate=traces,
            profiles_sample_rate=profiles,
            send_default_pii=False,
        )
    except Exception:
        # App must still boot without sentry installed.
        return


# Apply once with base's DEBUG (dev/prod will re-run after overriding DEBUG)
apply_runtime_defaults()
