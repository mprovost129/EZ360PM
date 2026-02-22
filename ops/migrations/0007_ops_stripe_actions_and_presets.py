from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0002_company_suspension_fields"),
        ("accounts", "0003_user_force_logout_at"),
        ("ops", "0006_opsactionlog"),
    ]

    operations = [
        migrations.CreateModel(
            name="OpsStripeAction",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("subscription_id_snapshot", models.CharField(blank=True, db_index=True, default="", max_length=120)),
                ("action_type", models.CharField(choices=[("cancel_at_period_end", "Cancel at period end"), ("resume", "Resume (uncancel)"), ("change_plan", "Change plan"), ("change_seats", "Change extra seats")], db_index=True, max_length=40)),
                ("status", models.CharField(choices=[("pending", "Pending"), ("approved", "Approved"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("canceled", "Canceled")], db_index=True, default="pending", max_length=16)),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("requested_by_email", models.EmailField(blank=True, db_index=True, default="", max_length=254)),
                ("requires_approval", models.BooleanField(db_index=True, default=True)),
                ("approved_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("approved_by_email", models.EmailField(blank=True, db_index=True, default="", max_length=254)),
                ("executed_at", models.DateTimeField(blank=True, db_index=True, null=True)),
                ("executed_by_email", models.EmailField(blank=True, db_index=True, default="", max_length=254)),
                ("idempotency_key", models.CharField(blank=True, db_index=True, default="", max_length=80)),
                ("error", models.TextField(blank=True, default="")),
                ("approved_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="approved_ops_stripe_actions", to="accounts.user")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ops_stripe_actions", to="companies.company")),
                ("executed_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="executed_ops_stripe_actions", to="accounts.user")),
                ("requested_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="requested_ops_stripe_actions", to="accounts.user")),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="OpsCompanyViewPreset",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=80, unique=True)),
                ("query_params", models.JSONField(blank=True, default=dict)),
                ("is_default", models.BooleanField(db_index=True, default=False)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddIndex(
            model_name="opsstripeaction",
            index=models.Index(fields=["status", "created_at"], name="ops_stripe_status_created_idx"),
        ),
        migrations.AddIndex(
            model_name="opsstripeaction",
            index=models.Index(fields=["company", "status", "created_at"], name="ops_stripe_co_st_cr_idx"),
        ),
        migrations.AddIndex(
            model_name="opsstripeaction",
            index=models.Index(fields=["action_type", "created_at"], name="ops_stripe_type_created_idx"),
        ),
    ]
