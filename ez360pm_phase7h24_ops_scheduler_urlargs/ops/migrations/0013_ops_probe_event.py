from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("ops", "0012_ops_email_test"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpsProbeEvent",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("kind", models.CharField(choices=[("sentry_test_error", "Sentry test error"), ("alert_test", "Alert test")], db_index=True, max_length=32)),
                ("status", models.CharField(choices=[("triggered", "Triggered"), ("completed", "Completed"), ("failed", "Failed")], db_index=True, default="triggered", max_length=16)),
                ("initiated_by_email", models.EmailField(blank=True, default="", max_length=254)),
                ("details", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="opsprobeevent",
            index=models.Index(fields=["kind", "status", "created_at"], name="ops_opsprob_kind_8ad0a5_idx"),
        ),
    ]
