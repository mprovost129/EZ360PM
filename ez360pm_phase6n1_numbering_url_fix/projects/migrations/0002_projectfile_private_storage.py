from django.db import migrations, models
import core.storages
import projects.models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectfile",
            name="file",
            field=models.FileField(upload_to=projects.models.project_file_upload_to, storage=core.storages.PrivateMediaStorage()),
        ),
    ]
