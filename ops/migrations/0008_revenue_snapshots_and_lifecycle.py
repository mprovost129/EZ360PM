from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0001_initial"),
        ("ops", "0007_ops_stripe_actions_and_presets"),
    ]

    operations = [
        migrations.CreateModel(
            name="CompanyLifecycleEvent",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("occurred_at", models.DateTimeField(db_index=True, default=timezone.now)),
                (
                    "event_type",
                    models.CharField(
                        choices=[
                            ("trial_started", "Trial started"),
                            ("trial_converted", "Trial converted"),
                            ("subscription_started", "Subscription started"),
                            ("subscription_canceled", "Subscription canceled"),
                            ("subscription_reactivated", "Subscription reactivated"),
                            ("company_suspended", "Company suspended"),
                            ("company_reactivated", "Company reactivated"),
                        ],
                        db_index=True,
                        max_length=48,
                    ),
                ),
                ("stripe_event_id", models.CharField(blank=True, db_index=True, default="", max_length=120)),
                ("details", models.JSONField(blank=True, default=dict)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="lifecycle_events",
                        to="companies.company",
                    ),
                ),
            ],
            options={
                "ordering": ["-occurred_at"],
            },
        ),
        migrations.AddIndex(
            model_name="companylifecycleevent",
            index=models.Index(fields=["event_type", "occurred_at"], name="ops_life_ev_type_oc_idx"),
        ),
        migrations.AddIndex(
            model_name="companylifecycleevent",
            index=models.Index(fields=["company", "event_type", "occurred_at"], name="ops_life_co_type_oc_idx"),
        ),
        migrations.CreateModel(
            name="PlatformRevenueSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True, unique=True)),
                ("active_subscriptions", models.PositiveIntegerField(default=0)),
                ("trialing_subscriptions", models.PositiveIntegerField(default=0)),
                ("past_due_subscriptions", models.PositiveIntegerField(default=0)),
                ("canceled_subscriptions", models.PositiveIntegerField(default=0)),
                ("mrr_cents", models.BigIntegerField(default=0)),
                ("arr_cents", models.BigIntegerField(default=0)),
                ("new_subscriptions_30d", models.PositiveIntegerField(default=0)),
                ("churned_30d", models.PositiveIntegerField(default=0)),
                ("reactivations_30d", models.PositiveIntegerField(default=0)),
                ("net_growth_30d", models.IntegerField(default=0)),
                ("revenue_at_risk_cents", models.BigIntegerField(default=0)),
                ("created_at", models.DateTimeField(default=timezone.now)),
            ],
            options={
                "ordering": ["-date"],
            },
        ),
    ]
