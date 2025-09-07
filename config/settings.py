# config/settings.py
from __future__ import annotations

from pathlib import Path
import os
from urllib.parse import urlparse

from dotenv import load_dotenv

# -----------------------------------------------------------------------------
# Paths & Env
# -----------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")  # load .env if present

# -----------------------------------------------------------------------------
# Core
# -----------------------------------------------------------------------------
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure")
DEBUG = os.getenv("DEBUG", "1") == "1"

# Comma-separated in env (e.g. "127.0.0.1,localhost,example.com")
ALLOWED_HOSTS = tuple(
    h.strip() for h in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()
)

# Site URL (use full origin incl. scheme in prod, e.g. "https://app.EZ360PM.com")
SITE_URL = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")

# Derive CSRF_TRUSTED_ORIGINS and ensure SITE_URL host is allowed
_parsed = urlparse(SITE_URL if "://" in SITE_URL else f"https://{SITE_URL}")
CSRF_TRUSTED_ORIGINS = [f"{_parsed.scheme}://{_parsed.hostname}"]
if _parsed.port:
    CSRF_TRUSTED_ORIGINS.append(f"{_parsed.scheme}://{_parsed.hostname}:{_parsed.port}")

if _parsed.hostname and _parsed.hostname not in ALLOWED_HOSTS:
    # Keep your explicit ALLOWED_HOSTS, but also allow the SITE_URL host
    ALLOWED_HOSTS = (*ALLOWED_HOSTS, _parsed.hostname)

# -----------------------------------------------------------------------------
# Apps
# -----------------------------------------------------------------------------
INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django.contrib.postgres",
    "widget_tweaks",

    # Local apps
    "accounts",
    "core.apps.CoreConfig",
    "billing",
    "dashboard",
    "timetracking",
    "clients.apps.ClientsConfig",
    "projects",
    "invoices",
    "company",
    "payments",
    "estimates",
    "expenses",
    "onboarding",
    "helpcenter",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "dashboard.middleware.OnboardingRedirectMiddleware",
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
                "company.context_processors.active_company",
                "core.context_processors.notifications",
                "core.context_processors.branding",
                "core.context_processors.app_context",
                "core.context_processors.app_globals",
                "dashboard.context_processors.cookie_consent",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# -----------------------------------------------------------------------------
# Database
# -----------------------------------------------------------------------------
# DB_ENGINE: "postgres" or "sqlite"
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()

if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "EZ360PM"),
            "USER": os.getenv("DB_USER", "postgres"),
            "PASSWORD": os.getenv("DB_PASSWORD", ""),
            "HOST": os.getenv("DB_HOST", "127.0.0.1"),
            "PORT": os.getenv("DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / os.getenv("DB_NAME", "db.sqlite3"),
        }
    }

# Optional caching (safe local-memory default; override via env if desired)
if os.getenv("CACHE_BACKEND", "").lower() == "redis":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://127.0.0.1:6379/1"),
            "TIMEOUT": int(os.getenv("CACHE_TIMEOUT", "300")),
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "TIMEOUT": int(os.getenv("CACHE_TIMEOUT", "300")),
        }
    }

# -----------------------------------------------------------------------------
# Auth
# -----------------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",                   # email-based login
    "django.contrib.auth.backends.ModelBackend",        # admin permissions etc.
]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------------------------------------------------------------
# I18N / TZ
# -----------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = os.getenv("TIME_ZONE", "America/New_York")
USE_I18N = True
USE_TZ = True

# -----------------------------------------------------------------------------
# Static / Media
# -----------------------------------------------------------------------------
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# -----------------------------------------------------------------------------
# Email
# -----------------------------------------------------------------------------
# For dev: console backend prints emails to the runserver console.
EMAIL_BACKEND = os.getenv("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = os.getenv("DEFAULT_FROM_EMAIL", "EZ360PM <no-reply@localhost>")
EMAIL_SUBJECT_PREFIX = os.getenv("EMAIL_SUBJECT_PREFIX", "[EZ360PM] ")
EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))

# (Optional) Production SMTP example (uncomment + set env vars)
# EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# EMAIL_HOST = os.getenv("EMAIL_HOST", "")
# EMAIL_PORT = int(os.getenv("EMAIL_PORT", "587"))
# EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
# EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
# EMAIL_USE_TLS = os.getenv("EMAIL_USE_TLS", "1") == "1"
# SERVER_EMAIL = DEFAULT_FROM_EMAIL

# -----------------------------------------------------------------------------
# Stripe
# -----------------------------------------------------------------------------
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "pk_test_...")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_...")

# -----------------------------------------------------------------------------
# App Settings (EZ360PM)
# -----------------------------------------------------------------------------
APP_NAME = os.getenv("APP_NAME", "EZ360PM")

# Estimates -> invoice behavior
ESTIMATE_PUBLIC_AUTO_INVOICE = os.getenv("ESTIMATE_PUBLIC_AUTO_INVOICE", "1") == "1"

# Invoices reminders: day offsets relative to due date
INVOICE_REMINDER_SCHEDULE = [int(x) for x in os.getenv("INVOICE_REMINDER_SCHEDULE", "-3,0,3,7,14").split(",")]

# Brand/legal
COMPANY_NAME = os.getenv("COMPANY_NAME", "EZ360PM")
COMPANY_ADDRESS = os.getenv("COMPANY_ADDRESS", "6 K Marie Drive, Attleboro, MA 02703")
SUPPORT_EMAIL = os.getenv("SUPPORT_EMAIL", "support@example.com")
LEGAL_EFFECTIVE_DATE = os.getenv("LEGAL_EFFECTIVE_DATE", "2025-08-31")  # YYYY-MM-DD
GOVERNING_LAW = os.getenv("GOVERNING_LAW", "Massachusetts, USA")

# Public links
DO_NOT_SELL_URL = os.getenv("DO_NOT_SELL_URL", "")
SUBPROCESSORS_URL = os.getenv("SUBPROCESSORS_URL", "/legal/subprocessors/")

# Cookie consent (frontend reads this value; non-HttpOnly)
COOKIE_CONSENT_NAME = os.getenv("COOKIE_CONSENT_NAME", "cookie_consent")
COOKIE_CONSENT_MAX_AGE = int(os.getenv("COOKIE_CONSENT_MAX_AGE", str(60 * 60 * 24 * 365)))  # 1 year

# Analytics (loaded only if user has consented)
PLAUSIBLE_DOMAIN = os.getenv("PLAUSIBLE_DOMAIN", "")   # e.g. "EZ360PM.com"
GA_MEASUREMENT_ID = os.getenv("GA_MEASUREMENT_ID", "") # e.g. "G-XXXXXXX"

# Publish subprocessors (used by a legal page)
SUBPROCESSORS = [
    {
        "name": "Amazon Web Services (AWS)",
        "purpose": "Cloud hosting, storage, networking",
        "data": "Application data, metadata, logs",
        "location": "United States (with regional variants)",
        "dpa_url": "https://aws.amazon.com/compliance/data-privacy-faq/",
    },
    {
        "name": "Stripe, Inc.",
        "purpose": "Payments, subscriptions, invoicing",
        "data": "Billing info, customer identifiers, metadata",
        "location": "United States/EU",
        "dpa_url": "https://stripe.com/legal/dpa",
    },
    {
        "name": "SendGrid / Twilio",
        "purpose": "Transactional email delivery",
        "data": "Recipient email, message metadata",
        "location": "United States",
        "dpa_url": "https://www.twilio.com/legal/data-protection-addendum",
    },
]

# -----------------------------------------------------------------------------
# Sessions & Cookies (good defaults; override via env as needed)
# -----------------------------------------------------------------------------
SESSION_COOKIE_AGE = int(os.getenv("SESSION_COOKIE_AGE", str(60 * 60 * 24 * 14)))  # 2 weeks
SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
CSRF_COOKIE_SAMESITE = os.getenv("CSRF_COOKIE_SAMESITE", "Lax")

# -----------------------------------------------------------------------------
# Logging (compact, production-friendly)
# -----------------------------------------------------------------------------
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DJANGO_LOG_LEVEL = os.getenv("DJANGO_LOG_LEVEL", "INFO")

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {"format": "%(levelname)s %(name)s: %(message)s"},
        "verbose": {"format": "%(asctime)s %(levelname)s %(name)s [%(module)s:%(lineno)d] %(message)s"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "simple"},
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": DJANGO_LOG_LEVEL, "propagate": False},
        "django.security.DisallowedHost": {  # avoid noisy tracebacks for healthchecks, etc.
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
}

# -----------------------------------------------------------------------------
# Security (recommended for production)
# -----------------------------------------------------------------------------
if not DEBUG:
    SECURE_SSL_REDIRECT = True
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

    # HSTS (enable once you're sure HTTPS is fully working)
    SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000"))  # 1 year
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

    # Additional safe headers
    SECURE_CONTENT_TYPE_NOSNIFF = True
    X_FRAME_OPTIONS = "DENY"
    SECURE_REFERRER_POLICY = os.getenv("SECURE_REFERRER_POLICY", "strict-origin-when-cross-origin")
    SECURE_CROSS_ORIGIN_OPENER_POLICY = os.getenv("SECURE_CROSS_ORIGIN_OPENER_POLICY", "same-origin")

# Optional: append slashes for nicer URLs
APPEND_SLASH = os.getenv("APPEND_SLASH", "1") == "1"
