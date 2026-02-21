# EZ360PM Deployment Guide (Pack Z)

This document covers a sane, repeatable production deployment for the EZ360PM web app.

## Settings modules
- Local development: `config.settings.dev`
- Production: `config.settings.prod`

Set via environment:
- `DJANGO_SETTINGS_MODULE=config.settings.prod`

## Required environment variables (minimum)
- `SECRET_KEY`
- `ALLOWED_HOSTS` (comma-separated, e.g. `ez360pm.com,www.ez360pm.com`)
- `CSRF_TRUSTED_ORIGINS` (comma-separated, full origins)
- `DATABASE_URL` (recommended) or the per-field DB vars used by your base settings
- `DJANGO_SETTINGS_MODULE=config.settings.prod`

## Recommended security env vars
- `SECURE_SSL_REDIRECT=1`
- `SESSION_COOKIE_SECURE=1`
- `CSRF_COOKIE_SECURE=1`
- `SECURE_HSTS_SECONDS=2592000` (30 days)
- `TRUST_X_FORWARDED_PROTO=1` (when behind a reverse proxy)

## Static and media
- Static is collected via: `python manage.py collectstatic --noinput`
- Media is served by your platform (S3/Render disk/NGINX). In dev it comes from local MEDIA.

## Typical deploy steps
1. Set environment variables
2. Install dependencies
3. Run migrations: `python manage.py migrate`
4. Collect static: `python manage.py collectstatic --noinput`
5. Create admin user: `python manage.py createsuperuser`
6. Start web process (example):
   - `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --log-file -`

## Health check
- `GET /health/` returns `{ "status": "ok", "service": "EZ360PM" }`
