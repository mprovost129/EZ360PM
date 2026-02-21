from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BankConnection",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("provider", models.CharField(default="plaid", max_length=32)),
                ("access_token", models.TextField(blank=True, default="")),
                ("item_id", models.CharField(blank=True, default="", max_length=128)),
                ("is_active", models.BooleanField(default=False)),
                ("last_sync_at", models.DateTimeField(blank=True, null=True)),
                ("last_sync_status", models.CharField(blank=True, default="", max_length=32)),
                ("last_sync_error", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="bank_connection",
                        to="companies.company",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="created_bank_connections",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="BankAccount",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("account_id", models.CharField(max_length=128)),
                ("name", models.CharField(blank=True, default="", max_length=128)),
                ("mask", models.CharField(blank=True, default="", max_length=8)),
                ("type", models.CharField(blank=True, default="", max_length=32)),
                ("subtype", models.CharField(blank=True, default="", max_length=64)),
                ("currency", models.CharField(blank=True, default="USD", max_length=8)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "connection",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="accounts",
                        to="integrations.bankconnection",
                    ),
                ),
            ],
            options={
                "unique_together": {("connection", "account_id")},
            },
        ),
        migrations.CreateModel(
            name="BankTransaction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("transaction_id", models.CharField(max_length=128)),
                ("posted_date", models.DateField(blank=True, null=True)),
                ("name", models.CharField(blank=True, default="", max_length=255)),
                ("amount_cents", models.IntegerField(default=0)),
                ("is_pending", models.BooleanField(default=False)),
                ("category", models.CharField(blank=True, default="", max_length=255)),
                ("raw", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "account",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transactions",
                        to="integrations.bankaccount",
                    ),
                ),
            ],
            options={
                "unique_together": {("account", "transaction_id")},
            },
        ),
        migrations.AddIndex(
            model_name="banktransaction",
            index=models.Index(fields=["posted_date"], name="integrations_posted_d_7a1cdb_idx"),
        ),
        migrations.AddIndex(
            model_name="banktransaction",
            index=models.Index(fields=["is_pending"], name="integrations_is_pend_9c3a7f_idx"),
        ),
    ]
