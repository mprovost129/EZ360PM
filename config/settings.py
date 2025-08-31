from pathlib import Path
import os
from dotenv import load_dotenv

# Build paths inside the project like this: BASE_DIR / 'subdir'.
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


# Quick-start development settings - unsuitable for production
# See https://docs.djangoproject.com/en/5.1/howto/deployment/checklist/

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure")

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = os.getenv("DEBUG", "1") == "1"

ALLOWED_HOSTS = "127.0.0.1", "localhost"


# Application definition

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    "django.contrib.postgres",
    # local
    "accounts",
    'core.apps.CoreConfig',
    "billing",
    "dashboard",
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    "dashboard.middleware.OnboardingRedirectMiddleware",
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / "templates"],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                "core.context_processors.active_company",
                "core.context_processors.notifications",
                "core.context_processors.branding",
                "core.context_processors.app_context",
                "core.context_processors.app_globals",
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'


# Database
# https://docs.djangoproject.com/en/5.1/ref/settings/#databases

# DB (Postgres or SQLite for dev)
DB_ENGINE = os.getenv("DB_ENGINE", "sqlite").lower()
if DB_ENGINE == "postgres":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("DB_NAME", "local_market"),
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


AUTH_USER_MODEL = "accounts.User"

AUTHENTICATION_BACKENDS = [
    "accounts.backends.EmailBackend",
    "django.contrib.auth.backends.ModelBackend",
]


# Password validation
# https://docs.djangoproject.com/en/5.1/ref/settings/#auth-password-validators

AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
     },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.1/topics/i18n/

LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.1/howto/static-files/

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# Default primary key field type
# https://docs.djangoproject.com/en/5.1/ref/settings/#default-auto-field

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Stripe
STRIPE_PUBLIC_KEY = os.getenv("STRIPE_PUBLIC_KEY", "pk_test_...")
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "sk_test_...")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "whsec_...")

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "dashboard:home"
LOGOUT_REDIRECT_URL = "accounts:login"

ESTIMATE_PUBLIC_AUTO_INVOICE = True  # or False if you only want status change

APP_NAME = "EZ360PM"
EMAIL_SUBJECT_PREFIX = "[EZ360PM] "
DEFAULT_FROM_EMAIL = "EZ360PM <no-reply@localhost>"

INVOICE_REMINDER_SCHEDULE = [-3, 0, 3, 7, 14]

COMPANY_NAME = "EZ360PM"
COMPANY_ADDRESS = "6 K Marie Drive, Attleboro, MA 02703"
SUPPORT_EMAIL = "mike@provosthomedesign.com"
SITE_URL = "www.ez360pm.com"
LEGAL_EFFECTIVE_DATE = "08-31-25"  # YYYY-MM-DD
GOVERNING_LAW = "Massachusetts, USA"

# Public links
DO_NOT_SELL_URL = ""              # e.g. "/privacy/opt-out/"
SUBPROCESSORS_URL = "/legal/subprocessors/"

# ---- Cookie consent
COOKIE_CONSENT_NAME = "cookie_consent"     # not HttpOnly—frontend must read it
COOKIE_CONSENT_MAX_AGE = 60 * 60 * 24 * 365  # 1 year

# Example analytics config (only loaded if analytics consent = ON)
PLAUSIBLE_DOMAIN = ""       # e.g. "ez360pm.com" (leave blank to skip)
GA_MEASUREMENT_ID = ""      # e.g. "G-XXXXXXX" (leave blank to skip)

# ---- Optional: publish subprocessors (name, purpose, data, location, dpa_url)
SUBPROCESSORS = [
    {
        "name": "Amazon Web Services (AWS)",
        "purpose": "Cloud hosting, storage, networking",
        "data": "Application data, metadata, logs",
        "location": "United States (with regional variants)",
        "dpa_url": "https://aws.amazon.com/compliance/data-privacy-faq/"
    },
    {
        "name": "Stripe, Inc.",
        "purpose": "Payments, subscriptions, invoicing",
        "data": "Billing info, customer identifiers, metadata",
        "location": "United States/EU",
        "dpa_url": "https://stripe.com/legal/dpa"
    },
    {
        "name": "SendGrid / Twilio",
        "purpose": "Transactional email delivery",
        "data": "Recipient email, message metadata",
        "location": "United States",
        "dpa_url": "https://www.twilio.com/legal/data-protection-addendum"
    },
]