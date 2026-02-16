from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("payables", "0002_migrate_crm_vendor"),
        ("companies", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BillAttachment",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("revision", models.BigIntegerField(default=0)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                (
                    "updated_by_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="updated_billattachment_set",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                ("updated_by_device", models.UUIDField(blank=True, null=True)),
                ("original_filename", models.CharField(blank=True, default="", max_length=240)),
                ("content_type", models.CharField(blank=True, default="", max_length=120)),
                ("file_s3_key", models.CharField(blank=True, default="", max_length=512)),
                (
                    "bill",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attachments",
                        to="payables.bill",
                    ),
                ),
                (
                    "uploaded_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="bill_attachments_uploaded",
                        to="companies.employeeprofile",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="billattachment",
            index=models.Index(fields=["bill"], name="payables_ba_bill_idx"),
        ),
    ]
