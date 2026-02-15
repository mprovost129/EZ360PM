from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("timetracking", "0002_performance_indexes"),
        ("catalog", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="timerstate",
            name="service_catalog_item",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="catalog.catalogitem"),
        ),
        migrations.AddField(
            model_name="timerstate",
            name="service_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
