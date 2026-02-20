"""WSGI config.

Set DJANGO_SETTINGS_MODULE to:
- config.settings.prod in production
- config.settings.dev locally

If not set, defaults to config.settings.dev.
"""

from __future__ import annotations

import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

application = get_wsgi_application()
