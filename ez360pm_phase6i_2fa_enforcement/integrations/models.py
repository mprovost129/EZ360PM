from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from companies.models import Company


class DropboxConnection(models.Model):
    """One Dropbox connection per company (v1)."""

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="dropbox_connection")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="created_dropbox_connections"
    )

    # WARNING: stored in DB. Consider encryption-at-rest later.
    access_token = models.TextField(blank=True, default="")
    account_id = models.CharField(max_length=128, blank=True, default="")
    token_type = models.CharField(max_length=32, blank=True, default="")
    scope = models.CharField(max_length=512, blank=True, default="")

    expires_at = models.DateTimeField(null=True, blank=True)

    is_active = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def mark_inactive(self) -> None:
        self.is_active = False
        self.save(update_fields=["is_active", "updated_at"])

    def __str__(self) -> str:
        return f"DropboxConnection(company={self.company_id}, active={self.is_active})"


class IntegrationConfig(models.Model):
    """Per-company integration preferences (v1)."""

    company = models.OneToOneField(Company, on_delete=models.CASCADE, related_name="integration_config")
    use_dropbox_for_project_files = models.BooleanField(
        default=False,
        help_text="If enabled, new Project Files will also be uploaded to Dropbox when connected.",
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"IntegrationConfig(company={self.company_id})"
