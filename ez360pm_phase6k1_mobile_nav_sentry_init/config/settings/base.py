from __future__ import annotations

import json
import os
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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


def _is_render() -> bool:
    return any(os.getenv(k) for k in ("RENDER", "RENDER_SERVICE_ID", "RENDER_EXTERNAL_URL", "RENDER_INSTANCE_ID"))


IS_RENDER = _is_render()


def _ensure_sslmode_require(db_url: str) -> str:
    """
    Ensure sslmode=require is present for Postgres URLs.
    On Render, Postgres expects SSL. This prevents the common 'SSL negotiation' error.
    """
    try:
        u = urlparse(db_url)
        scheme = (u.scheme or "").lower()
        if scheme not in {"postgres", "postgresql"}:
            return db_url

        qs = dict(parse_qsl(u.query, keep_blank_values=True))
        if "sslmode" not in qs:
            qs["sslmode"] = "require"
            u = u._replace(query=urlencode(qs))
            return urlunparse(u)
        return db_url
    except Exception:
        return db_url


# --------------------------------------------------------------------------------------
# Core
# --------------------------------------------------------------------------------------

# Debug defaults to OFF here. dev.py / prod.py own the authoritative toggle.
DEBUG = _getenv_bool("DEBUG", False)

SECRET_KEY = _getenv("SECRET_KEY", "django-insecure-CHANGE_ME")

# Hosts / origins (prod should set these via env; dev.py provides safe local defaults)
ALLOWED_HOSTS = [h.strip() for h in _getenv("ALLOWED_HOSTS", "").split(",") if h.strip()]
CSRF_TRUSTED_ORIGINS = [o.strip() for o in _getenv("CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Build / release metadata (safe to expose via /version and Ops)
APP_ENVIRONMENT = _getenv("APP_ENVIRONMENT", "")
BUILD_VERSION = _getenv("BUILD_VERSION", "")
BUILD_SHA = _getenv("BUILD_SHA", "") or _getenv("EZ360_RELEASE_SHA", "")
BUILD_DATE = _getenv("BUILD_DATE", "")

ENVIRONMENT = os.getenv("EZ360_ENV", "dev")
RELEASE_SHA = os.getenv("EZ360_RELEASE_SHA", "")


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

    # Presigned direct upload API (S3)
    "storage",
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

# Optional dependency for S3 media storage
if _getenv_bool("USE_S3", False):
    if "storages" not in INSTALLED_APPS:
        INSTALLED_APPS.append("storages")

AUTH_USER_MODEL = "accounts.User"


MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    # Serve static files in production (Render) without relying on platform static routes.
    # Safe in dev as well.
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "core.middleware.RequestIDMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.middleware.UserPresenceMiddleware",
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
#
# Priority order:
#  1) DATABASE_URL (Render recommended)
#  2) POSTGRES_* vars
#  3) legacy NAME/USER/PASSWORD/HOST/PORT vars
#  4) sqlite fallback (local boot convenience)
#
DATABASE_URL = _getenv("DATABASE_URL", "").strip()

if DATABASE_URL:
    if IS_RENDER:
        DATABASE_URL = _ensure_sslmode_require(DATABASE_URL)

    # Use dj-database-url if installed, else parse manually
    try:
        import dj_database_url  # type: ignore

        DATABASES = {
            "default": dj_database_url.parse(
                DATABASE_URL,
                conn_max_age=_getenv_int("DB_CONN_MAX_AGE", 600),
                ssl_require=IS_RENDER or _getenv_bool("DB_SSL_REQUIRE", False),
            )
        }
    except Exception:
        u = urlparse(DATABASE_URL)
        if u.scheme.lower() not in {"postgres", "postgresql"}:
            raise RuntimeError("DATABASE_URL must be a postgres:// URL")

        qs = dict(parse_qsl(u.query, keep_blank_values=True))
        options = {}
        if IS_RENDER and qs.get("sslmode") is None:
            options["sslmode"] = "require"

        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": (u.path or "").lstrip("/"),
                "USER": u.username or "",
                "PASSWORD": u.password or "",
                "HOST": u.hostname or "",
                "PORT": str(u.port or 5432),
                "CONN_MAX_AGE": _getenv_int("DB_CONN_MAX_AGE", 600),
                "OPTIONS": options,
            }
        }
else:
    # Discrete env var config
    db_name = _getenv("POSTGRES_DB", _getenv("NAME", "")).strip()
    db_user = _getenv("POSTGRES_USER", _getenv("USER", "")).strip()
    db_pass = _getenv("POSTGRES_PASSWORD", _getenv("PASSWORD", "")).strip()
    db_host = _getenv("POSTGRES_HOST", _getenv("HOST", "")).strip()
    db_port = _getenv("POSTGRES_PORT", _getenv("PORT", "")).strip()

    if db_host or db_name or db_user:
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.postgresql",
                "NAME": db_name or "ez360pm",
                "USER": db_user or "ez360pmuser",
                "PASSWORD": db_pass,
                "HOST": db_host or "localhost",
                "PORT": db_port or "5432",
                "CONN_MAX_AGE": _getenv_int("DB_CONN_MAX_AGE", 0),
                "OPTIONS": {"sslmode": "require"} if (IS_RENDER or _getenv_bool("DB_SSL_REQUIRE", False)) else {},
            }
        }
    else:
        # Local fallback so dev boots without any DB vars
        DATABASES = {
            "default": {
                "ENGINE": "django.db.backends.sqlite3",
                "NAME": str(BASE_DIR / "db.sqlite3"),
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


# --------------------------------------------------------------------------------------
# Media / file storage
# --------------------------------------------------------------------------------------

USE_S3 = _getenv_bool("USE_S3", False)

AWS_ACCESS_KEY_ID = _getenv("AWS_ACCESS_KEY_ID", "")
AWS_SECRET_ACCESS_KEY = _getenv("AWS_SECRET_ACCESS_KEY", "")
AWS_STORAGE_BUCKET_NAME = _getenv("AWS_STORAGE_BUCKET_NAME", "")
AWS_S3_REGION_NAME = _getenv("AWS_S3_REGION_NAME", "")
AWS_S3_ENDPOINT_URL = _getenv("AWS_S3_ENDPOINT_URL", "")
AWS_S3_CUSTOM_DOMAIN = _getenv("AWS_S3_CUSTOM_DOMAIN", "")
AWS_DEFAULT_ACL = _getenv("AWS_DEFAULT_ACL", "")

S3_PUBLIC_MEDIA_BUCKET = _getenv("S3_PUBLIC_MEDIA_BUCKET", "")
S3_PRIVATE_MEDIA_BUCKET = _getenv("S3_PRIVATE_MEDIA_BUCKET", "")
S3_PUBLIC_MEDIA_LOCATION = _getenv("S3_PUBLIC_MEDIA_LOCATION", "public-media")
S3_PRIVATE_MEDIA_LOCATION = _getenv("S3_PRIVATE_MEDIA_LOCATION", "private-media")
S3_PRIVATE_MEDIA_EXPIRE_SECONDS = int(_getenv("S3_PRIVATE_MEDIA_EXPIRE_SECONDS", "600") or "600")

S3_DIRECT_UPLOADS = _getenv_bool("S3_DIRECT_UPLOADS", False)
S3_PRESIGN_EXPIRE_SECONDS = int(_getenv("S3_PRESIGN_EXPIRE_SECONDS", "120") or "120")
S3_PRESIGN_MAX_SIZE_MB = int(_getenv("S3_PRESIGN_MAX_SIZE_MB", "50") or "50")

STORAGES: dict[str, dict[str, str] | dict[str, object]] = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # WhiteNoise provides compressed + hashed static assets for robust production serving.
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# WhiteNoise: allow referencing /static/* from finders during dev and collectstatic.
WHITENOISE_USE_FINDERS = True

# In CI/first deploy, a missing manifest can hard-fail if collectstatic didn't run.
# We keep strict by default, but allow opt-out via env for emergency recovery.
WHITENOISE_MANIFEST_STRICT = _getenv_bool("WHITENOISE_MANIFEST_STRICT", True)

if USE_S3:
    public_bucket = S3_PUBLIC_MEDIA_BUCKET or AWS_STORAGE_BUCKET_NAME
    STORAGES["default"] = {
        "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        "OPTIONS": {
            "bucket_name": public_bucket,
            "location": S3_PUBLIC_MEDIA_LOCATION,
            "default_acl": "public-read",
        },
    }

    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/{S3_PUBLIC_MEDIA_LOCATION.strip('/')}/"
    elif public_bucket:
        if AWS_S3_ENDPOINT_URL:
            MEDIA_URL = f"{AWS_S3_ENDPOINT_URL.rstrip('/')}/{public_bucket}/{S3_PUBLIC_MEDIA_LOCATION.strip('/')}/"
        else:
            MEDIA_URL = f"https://{public_bucket}.s3.amazonaws.com/{S3_PUBLIC_MEDIA_LOCATION.strip('/')}/"

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

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

TWO_FACTOR_ISSUER = _getenv("TWO_FACTOR_ISSUER", "EZ360PM")

RECAPTCHA_ENABLED = os.getenv("RECAPTCHA_ENABLED", "0") == "1"
RECAPTCHA_SITE_KEY = os.getenv("RECAPTCHA_SITE_KEY", "")
RECAPTCHA_SECRET_KEY = os.getenv("RECAPTCHA_SECRET_KEY", "")
RECAPTCHA_MIN_SCORE = float(os.getenv("RECAPTCHA_MIN_SCORE", "0.5"))

DROPBOX_APP_KEY = _getenv("DROPBOX_APP_KEY", "").strip()
DROPBOX_APP_SECRET = _getenv("DROPBOX_APP_SECRET", "").strip()
DROPBOX_REDIRECT_URI = _getenv("DROPBOX_REDIRECT_URI", "").strip()

EZ360_BACKUP_DIR = Path(_getenv("EZ360_BACKUP_DIR", str(BASE_DIR / "backups")))
EZ360_BACKUP_RETENTION_DAYS = _getenv_int("EZ360_BACKUP_RETENTION_DAYS", 14)
_backup_max_files_env = os.getenv("BACKUP_MAX_FILES")
BACKUP_MAX_FILES = int(_backup_max_files_env) if _backup_max_files_env not in (None, "") else None
EZ360_BACKUP_KEEP_LAST = _getenv_int("EZ360_BACKUP_KEEP_LAST", 14)

BACKUP_ENABLED = _getenv_bool("BACKUP_ENABLED", _getenv_bool("EZ360_BACKUP_ENABLED", False))
BACKUP_RETENTION_DAYS = _getenv_int("BACKUP_RETENTION_DAYS", EZ360_BACKUP_RETENTION_DAYS)
BACKUP_STORAGE = _getenv("BACKUP_STORAGE", "host_managed").strip()
_backup_notify_raw = _getenv("BACKUP_NOTIFY_EMAILS", "").strip()
BACKUP_NOTIFY_EMAILS = [e.strip() for e in _backup_notify_raw.split(",") if e.strip()]

EZ360_AUDIT_RETENTION_DAYS = _getenv_int("EZ360_AUDIT_RETENTION_DAYS", 365)
EZ360_STRIPE_WEBHOOK_RETENTION_DAYS = _getenv_int("EZ360_STRIPE_WEBHOOK_RETENTION_DAYS", 90)

OPS_ALERT_WEBHOOK_URL = _getenv("OPS_ALERT_WEBHOOK_URL", "").strip()
OPS_ALERT_WEBHOOK_TIMEOUT_SECONDS = float(_getenv("OPS_ALERT_WEBHOOK_TIMEOUT_SECONDS", "2.5") or 2.5)


# --------------------------------------------------------------------------------------
# Derived defaults
# --------------------------------------------------------------------------------------

def apply_runtime_defaults() -> None:
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

    _require_verify_env = os.getenv("ACCOUNTS_REQUIRE_EMAIL_VERIFICATION", "").strip()
    if _require_verify_env in {"0", "1"}:
        ACCOUNTS_REQUIRE_EMAIL_VERIFICATION = _require_verify_env == "1"
    else:
        ACCOUNTS_REQUIRE_EMAIL_VERIFICATION = not DEBUG

    ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS = int(
        os.getenv("ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS", str(60 * 60 * 24 * 3))
    )

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

    EZ360_CSP_ENABLED = _getenv_bool("EZ360_CSP_ENABLED", not DEBUG)
    SECURE_CSP_REPORT_ONLY = {
        "default-src": ["'self'"],
        "img-src": ["'self'", "data:"],
        "style-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "script-src": ["'self'", "'unsafe-inline'", "https://cdn.jsdelivr.net"],
        "font-src": ["'self'", "data:", "https://cdn.jsdelivr.net"],
        "connect-src": ["'self'"],
        "frame-ancestors": ["'none'"],
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

    _default_company_2fa_env = os.getenv("COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS", "").strip()
    if _default_company_2fa_env in {"0", "1"}:
        COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS = _default_company_2fa_env == "1"
    else:
        COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS = not DEBUG

    SLOW_REQUEST_THRESHOLD_MS = int(os.getenv("EZ360_SLOW_REQUEST_MS", "1500"))

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


# --------------------------------------------------------------------------------------
# Logging
# --------------------------------------------------------------------------------------

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "core.logging.RequestIDLogFilter"},
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s %(levelname)s %(name)s [rid=%(request_id)s] %(message)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": _getenv("DJANGO_LOG_LEVEL", "INFO")},
    "loggers": {
        "django.request": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "ez360pm.perf": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}


def init_sentry_if_configured() -> None:
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
        return


apply_runtime_defaults()

# Monitoring/Observability: initialize Sentry only when configured.
# Safe in dev/prod; no-op when SENTRY_DSN is unset.
init_sentry_if_configured()
