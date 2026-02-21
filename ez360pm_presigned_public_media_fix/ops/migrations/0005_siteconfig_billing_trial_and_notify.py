from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0004_rename_qa_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="billing_trial_days",
            field=models.PositiveSmallIntegerField(
                default=14,
                help_text="Number of free-trial days for new subscriptions created via Stripe Checkout.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="ops_notify_email_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, EZ360PM sends owner notifications for key lifecycle events (signups, conversions).",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="ops_notify_email_recipients",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Comma-separated list of recipient email addresses for ops notifications (separate from alerts).",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="ops_notify_on_company_signup",
            field=models.BooleanField(
                default=True,
                help_text="Notify when a new company is created (trial started).",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="ops_notify_on_subscription_active",
            field=models.BooleanField(
                default=True,
                help_text="Notify when a subscription becomes active (first successful renewal/payment).",
            ),
        ),
    ]
