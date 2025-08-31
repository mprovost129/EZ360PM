from django.db import migrations
from django.contrib.postgres.operations import TrigramExtension

class Migration(migrations.Migration):
    dependencies = [
        ("core", "0014_company_require_time_approval_timeentry_approved_at_and_more"),
    ]

    operations = [
        TrigramExtension(),
    ]
