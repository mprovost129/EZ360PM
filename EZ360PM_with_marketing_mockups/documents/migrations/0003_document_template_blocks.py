from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0002_document_composer_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="header_text",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="document",
            name="footer_text",
            field=models.TextField(blank=True, default=""),
        ),
    ]
