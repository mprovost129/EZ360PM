# sync/models.py
from __future__ import annotations

import uuid
from django.db import models
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company
from django.conf import settings


class DevicePlatform(models.TextChoices):
    WEB = "web", "Web"
    WINDOWS = "windows", "Windows"


class SyncDevice(SyncModel):
    """
    Represents a client device (desktop app instance).
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="devices")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    platform = models.CharField(max_length=20, choices=DevicePlatform.choices)
    name = models.CharField(max_length=120, blank=True, default="")

    last_seen_at = models.DateTimeField(null=True, blank=True)

    # LWW: optional monotonic counter per device (desktop increments locally)
    device_clock = models.BigIntegerField(default=0)


class SyncCursor(SyncModel):
    """
    Server-side cursor per (company, device) for incremental sync.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    device = models.ForeignKey(SyncDevice, on_delete=models.CASCADE)

    # ISO timestamp or server revision marker
    last_pulled_at = models.DateTimeField(null=True, blank=True)
    last_pushed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "device"], name="uniq_company_device_cursor")
        ]
