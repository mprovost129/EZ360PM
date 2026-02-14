# Monitoring & Observability (Phase 3H)

## Goals
- Detect failures fast (web errors, webhook processing errors, email delivery failures).
- Provide a reliable health endpoint for uptime monitors and deploy verification.
- Capture enough context to debug incidents (request ids, release sha, environment).

## Health endpoint
- `GET /healthz` (recommended)
  - Returns JSON with:
    - `ok` (always true if endpoint is reachable)
    - `db_ok` (true if DB ping succeeds)
    - `db_error` (only present if DB ping fails)
    - `env` (from `EZ360_ENV`)
    - `release` (from `EZ360_RELEASE_SHA`)
- `GET /health/` (legacy; wraps the same payload)

### Example response
```json
{
  "ok": true,
  "db_ok": true,
  "env": "prod",
  "release": "gitsha123..."
}
```

## Request IDs
- Every request is assigned a request id.
- Incoming header supported: `X-Request-ID`
- Response includes: `X-Request-ID`

## Slow request logging
- Requests slower than a threshold are logged at WARNING.
- Configure with:
  - `EZ360_SLOW_REQUEST_MS` (default 1500)

## Sentry (optional but recommended)
If `SENTRY_DSN` is set and `sentry-sdk` is installed, the app will auto-initialize Sentry in production settings.

Environment variables:
- `SENTRY_DSN`
- `SENTRY_ENVIRONMENT` (defaults to `EZ360_ENV`)
- `SENTRY_TRACES_SAMPLE_RATE` (default 0.05)
- `SENTRY_PROFILES_SAMPLE_RATE` (default 0.0)

Install dependency:
```bash
pip install sentry-sdk
```

## Webhook & email alerts
- Stripe webhook signature failures and processing exceptions are logged.
- Email send failures are logged and (if Sentry is enabled) captured.
