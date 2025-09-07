# core/apps.py
from __future__ import annotations

from django.apps import AppConfig


class CoreConfig(AppConfig):
    """App config for the core app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "core"

    def ready(self):
        # Import signal handlers
        try:
            import accounts.signals  # noqa: F401
        except Exception:
            # In dev/test environments signals may be absent; ignore safely.
            pass
