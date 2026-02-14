# projects/models.py
from __future__ import annotations

from django.db import models

from core.storages import PrivateMediaStorage
from django.utils import timezone

from core.models import SyncModel
from companies.models import Company, EmployeeProfile
from crm.models import Client
from catalog.models import CatalogItem


class ProjectBillingType(models.TextChoices):
    HOURLY = "hourly", "Hourly"
    FLAT = "flat", "Flat Rate"


class Project(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="projects")
    client = models.ForeignKey(Client, null=True, blank=True, on_delete=models.SET_NULL, related_name="projects")

    project_number = models.CharField(max_length=40, blank=True, default="")
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True, default="")

    date_received = models.DateField(null=True, blank=True)
    due_date = models.DateField(null=True, blank=True)

    billing_type = models.CharField(max_length=20, choices=ProjectBillingType.choices, default=ProjectBillingType.HOURLY)

    # flat rate or hourly
    flat_fee_cents = models.BigIntegerField(default=0)
    hourly_rate_cents = models.BigIntegerField(default=0)  # can be computed from employee rate, but allow override

    estimated_minutes = models.BigIntegerField(default=0)

    assigned_to = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="assigned_projects")

    is_active = models.BooleanField(default=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["company", "project_number"]),
        ]


class ProjectService(SyncModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="services")
    catalog_item = models.ForeignKey(CatalogItem, null=True, blank=True, on_delete=models.SET_NULL)

    name = models.CharField(max_length=200)
    notes = models.TextField(blank=True, default="")



def project_file_upload_to(instance: "ProjectFile", filename: str) -> str:
    # Keep paths stable and company-scoped
    return f"projects/{instance.company_id}/{instance.project_id}/{filename}"



class ProjectFile(SyncModel):
    company = models.ForeignKey(Company, on_delete=models.CASCADE, related_name="project_files")
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="files")
    uploaded_by = models.ForeignKey(EmployeeProfile, null=True, blank=True, on_delete=models.SET_NULL, related_name="uploaded_project_files")

    title = models.CharField(max_length=200, blank=True, default="")
    notes = models.TextField(blank=True, default="")
    file = models.FileField(upload_to=project_file_upload_to, storage=PrivateMediaStorage())

    storage_backend = models.CharField(
        max_length=20,
        choices=[('local', 'Local'), ('dropbox', 'Dropbox')],
        default='local',
    )
    dropbox_path = models.CharField(max_length=512, blank=True, default="")
    dropbox_shared_url = models.URLField(blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["company", "project", "created_at"]),
        ]
