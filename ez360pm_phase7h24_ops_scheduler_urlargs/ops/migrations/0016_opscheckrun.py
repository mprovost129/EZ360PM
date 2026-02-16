from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        ("ops", "0015_rename_ops_opsprob_kind_8ad0a5_idx_ops_opsprob_kind_a5da2a_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpsCheckRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("created_by_email", models.EmailField(blank=True, default="", max_length=254)),
                ("kind", models.CharField(choices=[("smoke", "Smoke Test"), ("invariants", "Invariants"), ("idempotency", "Idempotency Scan"), ("readiness", "Readiness Check")], db_index=True, max_length=32)),
                ("args", models.JSONField(blank=True, default=dict)),
                ("is_ok", models.BooleanField(db_index=True, default=False)),
                ("duration_ms", models.IntegerField(default=0)),
                ("output_text", models.TextField(blank=True, default="")),
                ("company", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="ops_check_runs", to="companies.company")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="opscheckrun",
            index=models.Index(fields=["kind", "created_at"], name="ops_opscheck_kind_crea_idx"),
        ),
        migrations.AddIndex(
            model_name="opscheckrun",
            index=models.Index(fields=["company", "created_at"], name="ops_opscheck_comp_crea_idx"),
        ),
        migrations.AddIndex(
            model_name="opscheckrun",
            index=models.Index(fields=["is_ok", "created_at"], name="ops_opscheck_ok_crea_idx"),
        ),
    ]
