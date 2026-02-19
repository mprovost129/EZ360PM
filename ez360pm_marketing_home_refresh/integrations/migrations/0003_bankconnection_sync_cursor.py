from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("integrations", "0002_bank_feed_scaffold"),
    ]

    operations = [
        migrations.AddField(
            model_name="bankconnection",
            name="sync_cursor",
            field=models.TextField(blank=True, default=""),
        ),
    ]
