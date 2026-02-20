# Generated manually for EZ360PM Phase 8X

from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("integrations", "0003_bankconnection_sync_cursor"),
        ("companies", "0001_initial"),
        ("expenses", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BankRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                ("priority", models.PositiveIntegerField(default=100, help_text="Lower runs first.")),
                (
                    "match_field",
                    models.CharField(
                        choices=[("name", "Merchant / Name"), ("category", "Bank category")],
                        default="name",
                        max_length=24,
                    ),
                ),
                (
                    "match_type",
                    models.CharField(
                        choices=[("contains", "Contains"), ("starts_with", "Starts with"), ("equals", "Equals")],
                        default="contains",
                        max_length=24,
                    ),
                ),
                ("match_text", models.CharField(max_length=160)),
                ("min_amount_cents", models.IntegerField(blank=True, null=True)),
                ("max_amount_cents", models.IntegerField(blank=True, null=True)),
                ("merchant_name", models.CharField(blank=True, default="", max_length=160)),
                ("expense_category", models.CharField(blank=True, default="", max_length=120)),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("suggest", "Suggest category"),
                            ("ignore", "Ignore"),
                            ("transfer", "Mark as transfer"),
                            ("auto_create_expense", "Auto-create draft expense"),
                        ],
                        default="suggest",
                        max_length=32,
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bank_rules",
                        to="companies.company",
                    ),
                ),
            ],
            options={
                "ordering": ["priority", "id"],
            },
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="status",
            field=models.CharField(
                choices=[
                    ("new", "New"),
                    ("ignored", "Ignored"),
                    ("transfer", "Transfer"),
                    ("expense_created", "Expense created"),
                ],
                default="new",
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="suggested_merchant_name",
            field=models.CharField(blank=True, default="", max_length=160),
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="suggested_category",
            field=models.CharField(blank=True, default="", max_length=120),
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="linked_expense",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="bank_transactions",
                to="expenses.expense",
            ),
        ),
        migrations.AddField(
            model_name="banktransaction",
            name="applied_rule",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="matched_transactions",
                to="integrations.bankrule",
            ),
        ),
    ]
