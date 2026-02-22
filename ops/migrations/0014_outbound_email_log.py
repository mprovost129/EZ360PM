from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0013_company_risk_snapshots_and_two_person"),
        ("companies", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="OutboundEmailLog",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("template_type", models.CharField(db_index=True, max_length=120)),
                ("to_email", models.EmailField(db_index=True, max_length=254)),
                ("subject", models.CharField(blank=True, default="", max_length=200)),
                ("provider_response_id", models.CharField(blank=True, default="", max_length=200)),
                (
                    "status",
                    models.CharField(
                        choices=[("sent", "Sent"), ("error", "Error")],
                        db_index=True,
                        max_length=12,
                    ),
                ),
                ("error_message", models.TextField(blank=True, default="")),
                (
                    "company",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="outbound_email_logs",
                        to="companies.company",
                    ),
                ),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="outboundemaillog",
            index=models.Index(fields=["status", "created_at"], name="ops_outbound_status_created_idx"),
        ),
        migrations.AddIndex(
            model_name="outboundemaillog",
            index=models.Index(fields=["template_type", "created_at"], name="ops_outbound_template_created_idx"),
        ),
        migrations.AddIndex(
            model_name="outboundemaillog",
            index=models.Index(fields=["company", "created_at"], name="ops_outbound_company_created_idx"),
        ),
    ]
