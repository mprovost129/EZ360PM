from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0011_siteconfig_risk_scoring"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="opscompanyviewpreset",
            name="owner",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name="ops_company_presets", to=settings.AUTH_USER_MODEL),
        ),
        migrations.AlterField(
            model_name="opscompanyviewpreset",
            name="name",
            field=models.CharField(max_length=80),
        ),
        migrations.AddConstraint(
            model_name="opscompanyviewpreset",
            constraint=models.UniqueConstraint(fields=("owner", "name"), name="uniq_ops_company_preset_owner_name"),
        ),
    ]
