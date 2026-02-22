from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("companies", "0002_company_suspension_fields"),
        ("ops", "0012_opscompanyviewpreset_owner"),
    ]

    operations = [
        migrations.AddField(
            model_name="siteconfig",
            name="ops_two_person_approval_enabled",
            field=models.BooleanField(
                default=False,
                help_text="When enabled, Stripe ops actions require two different staff users (requester cannot approve/run).",
            ),
        ),
        migrations.CreateModel(
            name="CompanyRiskSnapshot",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True)),
                ("risk_score", models.PositiveSmallIntegerField(default=0)),
                ("risk_level", models.CharField(blank=True, default="", max_length=16)),
                ("flags", models.JSONField(blank=True, default=list)),
                ("breakdown", models.JSONField(blank=True, default=list)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="risk_snapshots",
                        to="companies.company",
                    ),
                ),
            ],
            options={
                "ordering": ["-date", "company__name"],
            },
        ),
        migrations.AddConstraint(
            model_name="companyrisksnapshot",
            constraint=models.UniqueConstraint(fields=("company", "date"), name="uniq_company_risk_snapshot_day"),
        ),
        migrations.AddIndex(
            model_name="companyrisksnapshot",
            index=models.Index(fields=["date", "risk_level"], name="ops_risk_date_level_idx"),
        ),
    ]
