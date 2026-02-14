from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0009_remove_storagesmoketest_ops_storage_kind_d3ea22_idx_and_more"),
        ("companies", "0001_initial"),
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserPresence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("last_seen", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                (
                    "company",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="presence_rows", to="companies.company"),
                ),
                (
                    "user",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="presence_rows", to="accounts.user"),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["company", "last_seen"], name="ops_userpre_company_9f2c68_idx"),
                    models.Index(fields=["last_seen"], name="ops_userpre_last_se_1e4a0d_idx"),
                ],
                "unique_together": {("user", "company")},
            },
        ),
    ]
