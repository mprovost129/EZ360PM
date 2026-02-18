from __future__ import annotations

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("documents", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="sales_tax_percent",
            field=models.DecimalField(
                decimal_places=3,
                default=Decimal("0.000"),
                help_text="Sales tax percentage used for real-time totals and PDF display.",
                max_digits=6,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="deposit_type",
            field=models.CharField(
                choices=[("none", "None"), ("percent", "Percent"), ("fixed", "Fixed")],
                default="none",
                max_length=10,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="deposit_value",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="Percent (e.g., 25.00) or fixed amount (dollars) depending on deposit_type.",
                max_digits=12,
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="deposit_cents",
            field=models.BigIntegerField(
                default=0,
                help_text="Computed deposit requested in cents at time of last save.",
            ),
        ),
        migrations.AddField(
            model_name="document",
            name="terms",
            field=models.TextField(
                blank=True,
                default="",
                help_text="Invoice terms shown on customer-facing document.",
            ),
        ),
    ]
