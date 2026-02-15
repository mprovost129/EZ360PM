from __future__ import annotations

from django.db import migrations, models
from django.db.models import Q


class Migration(migrations.Migration):
    """Phase 3W: targeted indexes for TimeEntry list filters."""

    dependencies = [
        ("timetracking", "0001_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="timeentry",
            index=models.Index(
                fields=["company", "status", "started_at"],
                name="co_status_start_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ),
        migrations.AddIndex(
            model_name="timeentry",
            index=models.Index(
                fields=["company", "employee", "status", "started_at"],
                name="co_emp_status_start_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ),
        migrations.AddIndex(
            model_name="timeentry",
            index=models.Index(
                fields=["company", "billable", "started_at"],
                name="co_billable_start_live_idx",
                condition=Q(deleted_at__isnull=True),
            ),
        ),
    ]
