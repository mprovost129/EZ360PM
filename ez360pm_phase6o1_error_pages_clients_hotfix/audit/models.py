# audit/models.py
from __future__ import annotations

from django.db import models

from core.models import SyncModel
from companies.models import Company, EmployeeProfile


class AuditEvent(SyncModel):
    """
    Per-company audit log.
    Store everything: create/update/delete/export/login, billing, approvals, etc.
    """
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="audit_events")
    actor = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL)

    event_type = models.CharField(max_length=80)     # e.g. "invoice.sent", "time.approved"
    object_type = models.CharField(max_length=80)    # e.g. "Document"
    object_id = models.UUIDField(null=True, blank=True)

    summary = models.CharField(max_length=240, blank=True, default="")
    payload_json = models.JSONField(default=dict, blank=True)

    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["company", "event_type"]),
            models.Index(fields=["company", "created_at"]),
        ]
