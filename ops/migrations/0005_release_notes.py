from __future__ import annotations

from django.db import migrations, models
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0004_backup_models"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReleaseNote",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("environment", models.CharField(blank=True, db_index=True, default="", help_text="Deployment environment (dev/staging/prod). Optional, but recommended.", max_length=24)),
                ("build_version", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("build_sha", models.CharField(blank=True, db_index=True, default="", max_length=64)),
                ("title", models.CharField(max_length=200)),
                ("notes", models.TextField(blank=True, default="")),
                ("is_published", models.BooleanField(db_index=True, default=True, help_text="If disabled, note remains visible to staff but excluded from summaries.")),
                ("created_by_email", models.EmailField(blank=True, default="", max_length=254)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="releasenote",
            index=models.Index(fields=["environment", "created_at"], name="ops_releas_environment_8d0b27_idx"),
        ),
        migrations.AddIndex(
            model_name="releasenote",
            index=models.Index(fields=["build_version", "created_at"], name="ops_releas_build_ve_a0d8cf_idx"),
        ),
        migrations.AddIndex(
            model_name="releasenote",
            index=models.Index(fields=["build_sha", "created_at"], name="ops_releas_build_sh_7d53f6_idx"),
        ),
    ]
