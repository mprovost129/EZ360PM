# EZ360PM (Web)

EZ360PM is a multi-company, role-based CRM + accounting web app with subscription gating.

## Quick start (local)
1. Create a virtualenv and install requirements (your repo may manage deps separately).
2. Copy `.env.example` to `.env` and set `SECRET_KEY`.
3. Run migrations:
   - `python manage.py migrate`
4. Run server:
   - `python manage.py runserver`
5. Create admin:
   - `python manage.py createsuperuser`

## Production
- Use `DJANGO_SETTINGS_MODULE=config.settings.prod`
- Set `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS`
- Run:
  - `python manage.py migrate`
  - `python manage.py collectstatic --noinput`
  - `gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 3 --log-file -`

See:
- `docs/DEPLOYMENT.md`
- `docs/ENV_VARS.md`
