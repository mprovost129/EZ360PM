# helpcenter/models.py
from __future__ import annotations

from django.db import models
from django.utils import timezone


class HelpCenterScreenshot(models.Model):
    """
    Uploadable screenshots for Help Center pages.

    Phase 7H45:
    - Replace hard-coded static placeholders with DB-managed uploads (fallback to static).
    - Allows swapping in real screenshots without code changes.

    `key` should be a stable identifier used in templates (e.g. "accounting_overview").
    """

    key = models.SlugField(max_length=80, unique=True)
    title = models.CharField(max_length=120, blank=True, default="")
    image = models.ImageField(upload_to="helpcenter/screenshots/")
    updated_at = models.DateTimeField(default=timezone.now)

    def __str__(self) -> str:
        return self.title or self.key
