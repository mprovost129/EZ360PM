from __future__ import annotations

from django.conf import settings
from django.db import models


class UserNote(models.Model):
    """A lightweight, user-owned note record (call notes / intake notes).

    Notes are scoped to a company and owned by a user. In v1 we treat notes as
    private to the user who created them.
    """

    company = models.ForeignKey(
        "companies.Company",
        on_delete=models.CASCADE,
        related_name="user_notes",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="user_notes",
    )

    contact_name = models.CharField(max_length=200, blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=50, blank=True)

    subject = models.CharField(max_length=200)
    body = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["company", "created_by", "-created_at"], name="notes_company_user_created_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.subject}"
