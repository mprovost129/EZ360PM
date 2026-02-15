from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    """Phase 3W: targeted indexes for Documents list views."""

    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="document",
            index=models.Index(
                fields=["company", "doc_type", "created_at"],
                name="co_type_create_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ),
        migrations.AddIndex(
            model_name="document",
            index=models.Index(
                fields=["company", "doc_type", "status", "created_at"],
                name="co_type_status_create_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ),
    ]
