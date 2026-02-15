from __future__ import annotations

from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0003_launch_gate_items"),
    ]

    operations = [
        migrations.CreateModel(
            name="BackupRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("status", models.CharField(choices=[("success", "Success"), ("failed", "Failed")], db_index=True, default="success", max_length=16)),
                ("storage", models.CharField(blank=True, default="", max_length=64)),
                ("size_bytes", models.BigIntegerField(default=0)),
                ("notes", models.TextField(blank=True, default="")),
                ("initiated_by_email", models.EmailField(blank=True, default="", max_length=254)),
                ("details", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="BackupRestoreTest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("tested_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("outcome", models.CharField(choices=[("pass", "Pass"), ("fail", "Fail")], db_index=True, default="pass", max_length=8)),
                ("notes", models.TextField(blank=True, default="")),
                ("tested_by_email", models.EmailField(blank=True, default="", max_length=254)),
                ("details", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ["-tested_at"],
            },
        ),
        migrations.AddIndex(
            model_name="backuprun",
            index=models.Index(fields=["status", "created_at"], name="ops_backupru_status_7c705f_idx"),
        ),
        migrations.AddIndex(
            model_name="backuprestoretest",
            index=models.Index(fields=["outcome", "tested_at"], name="ops_backupre_outcome_2cfed5_idx"),
        ),
    ]
