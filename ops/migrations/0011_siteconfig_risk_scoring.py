from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0010_ops_roles"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="risk_payment_failed_window_days",
            field=models.PositiveSmallIntegerField(
                default=14,
                help_text="Lookback window (days) for Stripe payment failure signals used in tenant risk scoring.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_trial_ends_within_days",
            field=models.PositiveSmallIntegerField(
                default=7,
                help_text="Count a trial as 'ending soon' if it ends within this many days.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_weight_past_due",
            field=models.PositiveSmallIntegerField(default=60, help_text="Risk points added when a tenant subscription is past due."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_weight_mirror_stale",
            field=models.PositiveSmallIntegerField(default=25, help_text="Risk points added when Stripe mirror appears stale for the tenant."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_weight_payment_failed",
            field=models.PositiveSmallIntegerField(default=25, help_text="Risk points added when recent payment failure events are detected for the tenant."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_weight_payment_failed_sub_only",
            field=models.PositiveSmallIntegerField(default=10, help_text="Additional risk points when a payment failure event references a subscription but not the customer."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_weight_canceling",
            field=models.PositiveSmallIntegerField(default=15, help_text="Risk points added when the subscription is set to cancel at period end."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_weight_trial_ends_soon",
            field=models.PositiveSmallIntegerField(default=15, help_text="Risk points added when a trial ends within the configured window."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_level_medium_threshold",
            field=models.PositiveSmallIntegerField(default=40, help_text="Risk score threshold for medium risk level (inclusive)."),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="risk_level_high_threshold",
            field=models.PositiveSmallIntegerField(default=80, help_text="Risk score threshold for high risk level (inclusive)."),
        ),
    ]
