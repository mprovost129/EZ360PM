from __future__ import annotations

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


# SECURITY WARNING: keep the secret key used in production secret!
# Compatibility shim for DJANGO_SETTINGS_MODULE
import importlib
def _load_settings_shim():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    mod_name = os.environ.get("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    if mod_name in {"config.settings", "config.settings.py", "config.settings.shim"}:
        mod_name = "config.settings.dev"
    return importlib.import_module(mod_name)

_settings = _load_settings_shim()
for _k in dir(_settings):
    if _k.isupper():
        globals()[_k] = getattr(_settings, _k)
# Ensure DEBUG is defined
DEBUG = globals().get("DEBUG", _getenv_bool("DEBUG", False))
SECRET_KEY = _getenv("SECRET_KEY", "django-insecure-CHANGE_ME")


# Hosts / origins
ALLOWED_HOSTS = [h.strip() for h in _getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]

CSRF_TRUSTED_ORIGINS = [
    o.strip() for o in _getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()
]

ALLOWED_HOSTS = ["localhost", "127.0.0.1", "ez360pm.onrender.com", "ez360pm.com", "www.ez360pm.com"]
# Application definition
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


# Custom user model
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

    # Hardening gates (require messages + auth)
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


# Database
# Supports either:
# - DATABASE_URL (recommended)
# - or individual POSTGRES_* vars
# - or legacy NAME/USER/PASSWORD/HOST/PORT vars (kept for compatibility)
DATABASE_URL = _getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    # Optional: if you later add dj-database-url, you can switch to it.
    # For now, keep it simple and require POSTGRES_* or legacy vars.
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


# -------------------------
# Cache (performance hardening)
# -------------------------
EZ360_CACHE_ENABLED = _getenv_bool("EZ360_CACHE_ENABLED", False)

# Default to local memory cache. Optionally use Redis by setting REDIS_URL.
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



# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = _getenv("TIME_ZONE", "UTC")
USE_I18N = True
USE_TZ = True


# Static & media
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Project-level static (e.g., brand assets)
STATICFILES_DIRS = [
    BASE_DIR / "static",
]

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"


DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Django REST Framework
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": (
        "rest_framework.permissions.IsAuthenticated",
    ),
}


# EZ360PM constants
EZ360PM_TRIAL_DAYS = _getenv_int("EZ360PM_TRIAL_DAYS", 14)


# Auth UX defaults
LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/"
LOGOUT_REDIRECT_URL = "/"


# Human-friendly product name used in emails and other system messages
SITE_NAME = _getenv("SITE_NAME", "EZ360PM")


# SMTP (used when EMAIL_BACKEND is SMTP backend)
EMAIL_HOST = _getenv("EMAIL_HOST", "localhost")
EMAIL_PORT = _getenv_int("EMAIL_PORT", 587)
EMAIL_USE_TLS = _getenv_bool("EMAIL_USE_TLS", True)
EMAIL_HOST_USER = _getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = _getenv("EMAIL_HOST_PASSWORD", "")

DEFAULT_FROM_EMAIL = _getenv("DEFAULT_FROM_EMAIL", "info@ez360pm.com")
SERVER_EMAIL = _getenv("SERVER_EMAIL", DEFAULT_FROM_EMAIL)

# Support inbox (used for reply-to and user-facing contact links)
SUPPORT_EMAIL = _getenv("SUPPORT_EMAIL", "support@ez360pm.com")

# Optional: where replies should go (support inbox)
DEFAULT_REPLY_TO_EMAIL = _getenv("DEFAULT_REPLY_TO_EMAIL", SUPPORT_EMAIL).strip()

# Optional subject prefix for all outbound email (e.g. "[EZ360PM] ")
EMAIL_SUBJECT_PREFIX = _getenv("EMAIL_SUBJECT_PREFIX", "[EZ360PM] ")

# Security toggles (prod overrides)
# SECURE_PROXY_SSL_HEADER is now set in prod.py only


# ------------------------------
# Stripe (Subscriptions)
# ------------------------------
STRIPE_SECRET_KEY = _getenv("STRIPE_SECRET_KEY", "")
STRIPE_PUBLISHABLE_KEY = _getenv("STRIPE_PUBLISHABLE_KEY", "")
STRIPE_WEBHOOK_SECRET = _getenv("STRIPE_WEBHOOK_SECRET", "")

STRIPE_PORTAL_CONFIGURATION_ID = _getenv("STRIPE_PORTAL_CONFIGURATION_ID", "")

# Price map JSON (recommended keys): {"ez360pm_starter_monthly": "price_...", "ez360pm_pro_annual": "price_...", "ez360pm_seat_monthly": "price_..."}
# Legacy keys still supported: {"standard:solo": "price_...", "premium:up_to_5": "price_..."}
import json as _json  # noqa: E402

_raw_price_map = _getenv("STRIPE_PRICE_MAP_JSON", "")
STRIPE_PRICE_MAP = {}
if _raw_price_map:
    try:
        STRIPE_PRICE_MAP = _json.loads(_raw_price_map)
        if not isinstance(STRIPE_PRICE_MAP, dict):
            STRIPE_PRICE_MAP = {}
    except Exception:
        STRIPE_PRICE_MAP = {}



# Two-factor auth (TOTP)
TWO_FACTOR_ISSUER = os.environ.get('TWO_FACTOR_ISSUER', 'EZ360PM')

# -------------------------------------------------------------------
# Accounts / auth hardening
# -------------------------------------------------------------------
# Production defaults aim to be "secure by default" while keeping local dev friction low.
# Any of these can be overridden via environment variables.

# ---- Accounts / Verification ----
_require_verify_env = os.getenv("ACCOUNTS_REQUIRE_EMAIL_VERIFICATION", "").strip()
if _require_verify_env in {"0", "1"}:
    ACCOUNTS_REQUIRE_EMAIL_VERIFICATION = _require_verify_env == "1"
else:
    # Default ON in production, OFF in local/dev.
    ACCOUNTS_REQUIRE_EMAIL_VERIFICATION = not DEBUG

ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS = int(os.getenv("ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS", str(60 * 60 * 24 * 3)))


# ---- reCAPTCHA v3 (Pack Q) ----
RECAPTCHA_ENABLED = os.getenv("RECAPTCHA_ENABLED", "0") == "1"
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY", "")
RECAPTCHA_MIN_SCORE = float(os.getenv("RECAPTCHA_MIN_SCORE", "0.5"))


# -------------------------
# Dropbox Integration (Pack U)
# -------------------------
DROPBOX_APP_KEY = _getenv("DROPBOX_APP_KEY", "").strip()
DROPBOX_APP_SECRET = _getenv("DROPBOX_APP_SECRET", "").strip()
DROPBOX_REDIRECT_URI = _getenv("DROPBOX_REDIRECT_URI", "").strip()  # optional; default uses request.build_absolute_uri


# -------------------------
# Security hardening defaults
# -------------------------
# If you do nothing: production gets secure cookie + SSL defaults; local dev stays relaxed.
_secure_default = not DEBUG
## Security settings now set in dev.py and prod.py


# CSP: start in report-only mode by default
SECURE_CSP_REPORT_ONLY = {
    'default-src': ["'self'"],
    'img-src': ["'self'", 'data:'],
    'style-src': ["'self'", "'unsafe-inline'"],
    'script-src': ["'self'", "'unsafe-inline'"],
    'font-src': ["'self'", 'data:'],
    'connect-src': ["'self'"],
    'frame-ancestors': ["'none'"]
}
SECURE_CSP = {
    'default-src': ["'self'"],
    'img-src': ["'self'", 'data:'],
    'style-src': ["'self'", "'unsafe-inline'"],
    'script-src': ["'self'", "'unsafe-inline'"],
    'font-src': ["'self'", 'data:'],
    'connect-src': ["'self'"],
    'frame-ancestors': ["'none'"]
}


# ----------------------------------------
# Backups (Phase 3 – Backup & Recovery Pack)
# ----------------------------------------
# These are intentionally env-tunable. In production, set these to a persistent volume path.
EZ360_BACKUP_DIR = Path(_getenv("EZ360_BACKUP_DIR", str(BASE_DIR / "backups")))
EZ360_BACKUP_RETENTION_DAYS = _getenv_int("EZ360_BACKUP_RETENTION_DAYS", 14)
EZ360_BACKUP_KEEP_LAST = _getenv_int("EZ360_BACKUP_KEEP_LAST", 14)


ENVIRONMENT = os.getenv("EZ360_ENV", "dev")


RELEASE_SHA = os.getenv("EZ360_RELEASE_SHA", "")


# -------------------------
# Company security defaults
# -------------------------
_default_company_2fa_env = os.getenv("COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS", "").strip()
if _default_company_2fa_env in {"0", "1"}:
    COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS = _default_company_2fa_env == "1"
else:
    # Default ON in production.
    COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS = not DEBUG


SLOW_REQUEST_THRESHOLD_MS = int(os.getenv("EZ360_SLOW_REQUEST_MS", "1500"))


# ----------------------------------------
# Ops retention / pruning (Phase 3 – Ops Alerts + Retention Pack)
# ----------------------------------------
# Keep these env-tunable so ops can change retention without migrations.
EZ360_AUDIT_RETENTION_DAYS = _getenv_int("EZ360_AUDIT_RETENTION_DAYS", 365)
EZ360_STRIPE_WEBHOOK_RETENTION_DAYS = _getenv_int("EZ360_STRIPE_WEBHOOK_RETENTION_DAYS", 90)

# Optional: send ops alert emails on scheduled checks/prune jobs.
# Format: "Name:email,Name2:email2". If empty, no ops emails are sent.
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
