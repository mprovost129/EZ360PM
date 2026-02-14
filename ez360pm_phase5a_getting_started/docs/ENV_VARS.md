# EZ360PM Environment Variables

This app is designed to run with env-driven configuration.

## Core
- `DJANGO_SETTINGS_MODULE` (`config.settings.dev` or `config.settings.prod`)
- `SECRET_KEY`
- `DEBUG` (dev only)
- `ALLOWED_HOSTS` (prod)
- `CSRF_TRUSTED_ORIGINS` (prod)

## Database
Depending on your base settings, use either:
- `DATABASE_URL`
or
- per-field DB vars (host, name, user, password, port)

## Email (SES / SMTP)
- `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`
- `EMAIL_HOST`
- `EMAIL_PORT=587`
- `EMAIL_HOST_USER`
- `EMAIL_HOST_PASSWORD`
- `EMAIL_USE_TLS=1`
- `DEFAULT_FROM_EMAIL=no-reply@localmarkene.com`
- `SUPPORT_EMAIL=support@localmarkene.com`

## Stripe (optional until configured)
- `STRIPE_SECRET_KEY`
- `STRIPE_PUBLISHABLE_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_PRICE_MAP_JSON` (recommended: lookup_key -> price_id; e.g. ez360pm_starter_monthly -> price_...)
- `STRIPE_PORTAL_CONFIGURATION_ID` (optional)

## reCAPTCHA v3 (optional)
- `RECAPTCHA_ENABLED=1`
- `RECAPTCHA_SITE_KEY`
- `RECAPTCHA_SECRET_KEY`
- `RECAPTCHA_MIN_SCORE=0.5`

## Security / Auth Hardening

- `ACCOUNTS_REQUIRE_EMAIL_VERIFICATION` ("1"/"0")
  - If not set, defaults to **ON in production (DEBUG=False)**, OFF in local dev.
- `ACCOUNTS_VERIFY_EMAIL_MAX_AGE_SECONDS` (default 3 days)
- `COMPANY_DEFAULT_REQUIRE_2FA_ADMINS_MANAGERS` ("1"/"0")
  - If not set, defaults to **ON in production (DEBUG=False)**.

## CSP (Content Security Policy)

- `EZ360_CSP_ENABLED` ("1"/"0")
  - Default: **ON in production**, OFF in dev.
- `EZ360_CSP_REPORT_ONLY` ("1"/"0")
  - Default: **Report-only in production**. Set to 0 to enforce CSP.

## Caching (optional)
- `EZ360_CACHE_ENABLED=1`
- `REDIS_URL` (optional, if using Redis cache)

## Dropbox (optional)

## Development-only overrides

- `DEV_SECURE_SSL_REDIRECT` (default: `0`)
  - If set to `1`, forces `SECURE_SSL_REDIRECT=True` in `config/settings/dev.py`.
  - Only use this if you run a local HTTPS-capable server; otherwise keep it `0` so local dev stays reachable via plain HTTP.
- `DROPBOX_APP_KEY`
- `DROPBOX_APP_SECRET`
- `DROPBOX_REDIRECT_URI` (optional)


## Monitoring / Observability
- EZ360_RELEASE_SHA (optional, e.g. git SHA for deploy traceability)
- EZ360_SLOW_REQUEST_MS (default 1500)
- EZ360_PERF_LOGGING_ENABLED ("1"/"0"; dev/staging friendly)
- EZ360_PERF_REQUEST_MS (default 600)
- EZ360_PERF_QUERY_MS (default 120; requires DEBUG to collect connection.queries)
- EZ360_PERF_TOP_N (default 5)
- EZ360_PERF_SAMPLE_RATE (0.0–1.0; default 1.0)
- EZ360_PERF_STORE_DB ("1"/"0"; if enabled, stores sampled slow-request alerts to DB)
- SENTRY_DSN (optional)
- SENTRY_ENVIRONMENT (optional; defaults to EZ360_ENV)
- SENTRY_TRACES_SAMPLE_RATE (optional; default 0.05)
- SENTRY_PROFILES_SAMPLE_RATE (optional; default 0.0)

## Ops Retention / Pruning

- `EZ360_AUDIT_RETENTION_DAYS` — prune `audit.AuditEvent` older than this (default 365)
- `EZ360_STRIPE_WEBHOOK_RETENTION_DAYS` — prune `billing.BillingWebhookEvent` older than this (default 90)
- `EZ360_ADMINS` — optional admin emails for ops alerts (format: `Name:email,Name2:email2`)
- `EZ360_ALERT_ON_WEBHOOK_FAILURE` — send immediate admin email when Stripe webhook processing fails (default: ON in production)
- `EZ360_ALERT_ON_EMAIL_FAILURE` — send immediate admin email when email sending fails (default: ON in production)
