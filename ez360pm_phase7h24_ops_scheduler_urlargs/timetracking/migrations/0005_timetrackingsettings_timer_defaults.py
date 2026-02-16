from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("catalog", "0001_initial"),
        ("projects", "0001_initial"),
        ("timetracking", "0004_timerstate_pause_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="timetrackingsettings",
            name="last_project",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="time_settings_last_project",
                to="projects.project",
            ),
        ),
        migrations.AddField(
            model_name="timetrackingsettings",
            name="last_service_catalog_item",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="time_settings_last_service",
                to="catalog.catalogitem",
            ),
        ),
        migrations.AddField(
            model_name="timetrackingsettings",
            name="last_service_name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
        migrations.AddField(
            model_name="timetrackingsettings",
            name="last_note",
            field=models.TextField(blank=True, default=""),
        ),
    ]
