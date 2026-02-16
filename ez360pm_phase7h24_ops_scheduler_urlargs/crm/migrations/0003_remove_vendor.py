from __future__ import annotations

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("crm", "0002_client_company_email_index"),
        ("expenses", "0003_alter_expense_vendor_to_payables"),
    ]

    operations = [
        migrations.DeleteModel(
            name="Vendor",
        ),
    ]
