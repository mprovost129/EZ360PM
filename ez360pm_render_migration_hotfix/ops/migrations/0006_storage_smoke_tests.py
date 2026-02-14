from __future__ import annotations

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("ops", "0005_release_notes"),
    ]

    operations = [
        migrations.CreateModel(
            name="StorageSmokeTest",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, db_index=True)),
                ("kind", models.CharField(choices=[("receipt_upload", "Receipt upload"), ("receipt_download", "Receipt download"), ("project_upload", "Project file upload"), ("project_download", "Project file download")], db_index=True, max_length=32)),
                ("ok", models.BooleanField(db_index=True, default=False)),
                ("message", models.CharField(blank=True, default="", max_length=240)),
                ("object_name", models.CharField(blank=True, default="", max_length=512)),
                ("details", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="storagesmoketest",
            index=models.Index(fields=["kind", "created_at"], name="ops_storag_kind_3bf9aa_idx"),
        ),
        migrations.AddIndex(
            model_name="storagesmoketest",
            index=models.Index(fields=["ok", "created_at"], name="ops_storag_ok_4b4b4b_idx"),
        ),
    ]
