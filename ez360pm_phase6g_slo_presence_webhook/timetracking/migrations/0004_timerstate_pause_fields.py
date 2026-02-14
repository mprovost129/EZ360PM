from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("timetracking", "0003_timerstate_service_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="timerstate",
            name="is_paused",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="timerstate",
            name="paused_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="timerstate",
            name="elapsed_seconds",
            field=models.BigIntegerField(default=0),
        ),
    ]
