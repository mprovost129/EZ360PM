from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("payables", "0002_migrate_crm_vendor"),
        ("expenses", "0002_expense_receipt_private_storage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="expense",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                to="payables.vendor",
            ),
        ),
    ]
