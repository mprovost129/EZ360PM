from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0002_subscription_overrides"),
    ]

    operations = [
        migrations.AddField(
            model_name="companysubscription",
            name="ops_notified_active_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
