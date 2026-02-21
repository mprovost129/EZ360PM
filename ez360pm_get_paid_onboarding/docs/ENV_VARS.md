# EZ360PM Environment Variables

This app is designed to run with env-driven configuration.

## Core
- `DJANGO_SETTINGS_MODULE` (`config.settings.dev` or `config.settings.prod`)
- `SECRET_KEY`
- `DEBUG` (dev only)
- `ALLOWED_HOSTS` (prod)
- `CSRF_TRUSTED_ORIGINS` (prod)

## Static files (Render / production)

- `WHITENOISE_MANIFEST_STRICT` (default: 1)
  - When 1, WhiteNoise raises an error if the static manifest is missing (collectstatic did not run).
  - Set to 0 temporarily only to recover a bad deploy while you fix your Render build pipeline.

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

- `TWO_FACTOR_ISSUER` (default: EZ360PM)
- `TWO_FACTOR_SESSION_TTL_SECONDS` (default: 43200 / 12 hours)
  - How long a 2FA confirmation remains valid for the current session before another step-up is required.

## CSP (Content Security Policy)

- `EZ360_CSP_ENABLED` ("1"/"0")
  - Default: **ON in production**, OFF in dev.
- `EZ360_CSP_REPORT_ONLY` ("1"/"0")
  - Default: **Report-only in production**. Set to 0 to enforce CSP.

## Caching (optional)
- `EZ360_CACHE_ENABLED=1`
- `REDIS_URL` (optional, if using Redis cache)

## Dropbox (optional)

- `DROPBOX_APP_KEY`
- `DROPBOX_APP_SECRET`
- `DROPBOX_REDIRECT_URI` (optional)

## Bank feeds (optional; scaffold)

- `PLAID_ENABLED` ("1"/"0"; default `0`)
- `PLAID_CLIENT_ID`
- `PLAID_SECRET`
- `PLAID_ENV` (default `sandbox`)

## Development-only overrides

- `DEV_SECURE_SSL_REDIRECT` (default: `0`)
  - If set to `1`, forces `SECURE_SSL_REDIRECT=True` in `config/settings/dev.py`.
  - Only use this if you run a local HTTPS-capable server; otherwise keep it `0` so local dev stays reachable via plain HTTP.


## Monitoring / Observability
- Build / release metadata (optional, recommended)
  - `APP_ENVIRONMENT` (dev|staging|prod)
  - `BUILD_VERSION` (optional semantic version/tag)
  - `BUILD_SHA` (git SHA; falls back to `EZ360_RELEASE_SHA` if set)
  - `BUILD_DATE` (ISO timestamp)

- `EZ360_RELEASE_SHA` (legacy alias; optional)
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

## Ops / Health

- `HEALTHCHECK_TOKEN` (optional)
  - If set, enables `GET /health/details/` which requires the token.
  - Provide token via `X-Health-Token` header or `?token=` query.

## Ops Retention / Pruning

- `EZ360_AUDIT_RETENTION_DAYS` — prune `audit.AuditEvent` older than this (default 365)
- `EZ360_STRIPE_WEBHOOK_RETENTION_DAYS` — prune `billing.BillingWebhookEvent` older than this (default 90)
- `EZ360_ADMINS` — optional admin emails for ops alerts (format: `Name:email,Name2:email2`)
- `EZ360_ALERT_ON_WEBHOOK_FAILURE` — send immediate admin email when Stripe webhook processing fails (default: ON in production)
- `EZ360_ALERT_ON_EMAIL_FAILURE` — send immediate admin email when email sending fails (default: ON in production)


## Backups (Phase 6C)
- `BACKUP_ENABLED` (default 0): Enables backup visibility flags (does not run backups).
- `DEV_BACKUP_ENABLED` (default 0): Dev-only override; keeps dev safe.
- `BACKUP_STORAGE` (default host_managed): host_managed|s3|local.
- `BACKUP_RETENTION_DAYS` (default 30)
- `BACKUP_MAX_FILES` (default None): If set, keep only newest N backups (count-based retention).
- `BACKUP_NOTIFY_EMAILS` (CSV, optional)


### Release / Preflight
- `PREFLIGHT_REQUIRE_NO_PENDING_MIGRATIONS` — default `1`. If enabled, `python manage.py ez360_preflight` exits non-zero when pending migrations are detected.


## Backups (automation)

- `EZ360_PG_DUMP_PATH` (optional): Full path to `pg_dump` if it is not on PATH.
- `BACKUP_ENABLED`: Set `1` to allow `python manage.py ez360_backup_db` to run without `--force`.
- `EZ360_BACKUP_DIR`: Output directory for backups (default: `<BASE_DIR>/backups`).
- `BACKUP_STORAGE`: Label stored on BackupRun rows (e.g. `host_managed`, `local`, `s3`).


## Backups (scheduling guidance)
See `docs/BACKUPS.md` for cron / Task Scheduler examples and restore-test recording.


## Media storage (optional S3)
- `USE_S3` (0/1) — enable S3/S3-compatible storage for uploaded media (requires `django-storages[boto3]`)
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_STORAGE_BUCKET_NAME`
- `AWS_S3_REGION_NAME`
- `AWS_S3_ENDPOINT_URL` (optional)
- `AWS_S3_CUSTOM_DOMAIN` (optional, recommended)
- `AWS_DEFAULT_ACL` (optional)

See `docs/MEDIA_STORAGE.md` for setup notes.



## S3 Media Storage (Multi-bucket)

- `USE_S3` (0/1)
- `S3_PUBLIC_MEDIA_BUCKET`
- `S3_PRIVATE_MEDIA_BUCKET`
- `S3_PUBLIC_MEDIA_LOCATION` (default `public-media`)
- `S3_PRIVATE_MEDIA_LOCATION` (default `private-media`)
- `S3_PRIVATE_MEDIA_EXPIRE_SECONDS` (default `600`) — presigned URL lifetime for private files (receipts, project files)

Fallback (single bucket): `AWS_STORAGE_BUCKET_NAME`

### S3 Direct Uploads

- `S3_DIRECT_UPLOADS` (0/1) — enable browser direct uploads to S3 using presigned POST.
- `S3_PRESIGN_MAX_SIZE_MB` — max upload size enforced by the presigned policy.
- `S3_PRESIGN_EXPIRE_SECONDS
S3_PRESIGN_DOWNLOAD_EXPIRE_SECONDS` — presigned policy expiry.

See `docs/MEDIA_STORAGE.md` for required bucket CORS configuration.


## Ops Alerts (optional external webhook)

- `OPS_ALERT_WEBHOOK_URL` — if set, ops alerts will POST a small JSON payload to this URL (best-effort).
- `OPS_ALERT_WEBHOOK_TIMEOUT_SECONDS` (default `2.5`) — HTTP timeout for webhook delivery.
