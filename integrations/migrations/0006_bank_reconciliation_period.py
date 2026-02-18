from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("integrations", "0005_bank_review_queue_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="BankReconciliationPeriod",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("status", models.CharField(choices=[("open", "Open"), ("locked", "Locked")], default="open", max_length=12)),
                ("locked_at", models.DateTimeField(blank=True, null=True)),
                ("notes", models.TextField(blank=True, default="")),
                ("snapshot_bank_outflow_cents", models.BigIntegerField(default=0)),
                ("snapshot_expense_total_cents", models.BigIntegerField(default=0)),
                ("snapshot_matched_count", models.PositiveIntegerField(default=0)),
                ("snapshot_unmatched_bank_count", models.PositiveIntegerField(default=0)),
                ("snapshot_unmatched_expense_count", models.PositiveIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="bank_reconciliation_periods", to="companies.company"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_bank_reconciliation_periods",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "locked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="locked_bank_reconciliation_periods",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ["-start_date", "-id"],
            },
        ),
        migrations.AddIndex(
            model_name="bankreconciliationperiod",
            index=models.Index(fields=["company", "start_date", "end_date"], name="intg_co_s_e_idx"),
        ),
        migrations.AddIndex(
            model_name="bankreconciliationperiod",
            index=models.Index(fields=["company", "status"], name="intg_co_status_idx"),
        ),
    ]
