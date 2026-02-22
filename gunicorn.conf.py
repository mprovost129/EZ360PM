"""Gunicorn configuration for Render.

This file is intentionally safe-by-default for small instances.

Render typically launches Gunicorn via a Start Command (Dashboard setting).
Recommended Start Command:

    gunicorn config.wsgi:application --bind 0.0.0.0:$PORT -c gunicorn.conf.py

Or, if you prefer keeping the start command unchanged, set Render env var:

    GUNICORN_CMD_ARGS="-c gunicorn.conf.py"

Key goals:
- Avoid OOM restarts by keeping worker count conservative.
- Mitigate memory creep by recycling workers (max_requests).
- Prevent false downtime from occasional slow responses while you harden endpoints.

Tune via env vars as needed.
"""

from __future__ import annotations

import os


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(str(raw).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return float(str(raw).strip())
    except Exception:
        return default


# -----------------------------------------------------------------------------
# Core bind/logging
# -----------------------------------------------------------------------------

bind = os.getenv("GUNICORN_BIND", "0.0.0.0:" + (os.getenv("PORT") or "10000"))
accesslog = "-"  # stdout
errorlog = "-"   # stderr
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")


# -----------------------------------------------------------------------------
# Concurrency (keep conservative to avoid OOM on small instances)
# -----------------------------------------------------------------------------

# If you know your Render instance has >= 2GB RAM, you can raise this.
workers = _env_int("WEB_CONCURRENCY", 2)
worker_class = os.getenv("GUNICORN_WORKER_CLASS", "sync")
threads = _env_int("GUNICORN_THREADS", 1)


# -----------------------------------------------------------------------------
# Timeouts
# -----------------------------------------------------------------------------

# Default Gunicorn timeout is 30s; increase slightly to reduce worker-kill churn
# while you harden expensive endpoints.
# NOTE: Long-running work should be moved out of request/response (Celery/RQ) in v1.1.

timeout = _env_int("GUNICORN_TIMEOUT", 60)
graceful_timeout = _env_int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _env_int("GUNICORN_KEEPALIVE", 5)


# -----------------------------------------------------------------------------
# Memory creep mitigation
# -----------------------------------------------------------------------------

# Recycle workers periodically to protect against slow memory growth in long-lived
# processes (common with Python apps under load).
max_requests = _env_int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _env_int("GUNICORN_MAX_REQUESTS_JITTER", 100)


# -----------------------------------------------------------------------------
# Misc hardening
# -----------------------------------------------------------------------------

# Preload is OFF by default. Turning it ON can reduce memory footprint via COW
# *if* your app is preload-safe. Leave OFF until you verify startup.
preload_app = os.getenv("GUNICORN_PRELOAD_APP", "false").strip().lower() in {"1", "true", "yes", "on"}
