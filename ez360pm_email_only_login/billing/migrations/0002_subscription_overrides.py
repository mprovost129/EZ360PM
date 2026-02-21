from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="companysubscription",
            name="is_comped",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="companysubscription",
            name="comped_until",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="companysubscription",
            name="comped_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="companysubscription",
            name="discount_percent",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="companysubscription",
            name="discount_note",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="companysubscription",
            name="discount_ends_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
