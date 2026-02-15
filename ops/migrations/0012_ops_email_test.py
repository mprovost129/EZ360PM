from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0011_rename_ops_userpre_company_9f2c68_idx_ops_userpre_company_f4154b_idx_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpsEmailTest",
            fields=[
                ("id", models.BigAutoField(primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("to_email", models.EmailField(max_length=254)),
                ("subject", models.CharField(max_length=200)),
                ("backend", models.CharField(blank=True, default="", max_length=255)),
                ("from_email", models.CharField(blank=True, default="", max_length=254)),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "Sent"), ("failed", "Failed")],
                        default="sent",
                        max_length=20,
                    ),
                ),
                ("latency_ms", models.PositiveIntegerField(default=0)),
                ("error", models.TextField(blank=True, default="")),
                ("initiated_by_email", models.EmailField(blank=True, default="", max_length=254)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="opsemailtest",
            index=models.Index(fields=["created_at"], name="ops_opsemail_created_0c2b79_idx"),
        ),
        migrations.AddIndex(
            model_name="opsemailtest",
            index=models.Index(fields=["status", "created_at"], name="ops_opsemail_status_9c780a_idx"),
        ),
    ]
