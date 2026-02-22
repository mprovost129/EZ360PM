from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0008_revenue_snapshots_and_lifecycle"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="stripe_mirror_stale_after_hours",
            field=models.PositiveSmallIntegerField(
                default=48,
                help_text="If no Stripe subscription event updates the mirror within this window, create a drift alert.",
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="stripe_mirror_stale_alert_level",
            field=models.CharField(
                choices=[("info", "Info"), ("warn", "Warning"), ("error", "Error")],
                default="warn",
                help_text="Alert level used when Stripe mirror drift is detected.",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="siteconfig",
            name="ops_require_2fa_for_critical_actions",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, critical ops actions require a valid 2FA session (in addition to typed confirmations).",
            ),
        ),
    ]
