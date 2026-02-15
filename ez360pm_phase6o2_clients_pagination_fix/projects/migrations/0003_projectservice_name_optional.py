from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0002_projectfile_private_storage"),
    ]

    operations = [
        migrations.AlterField(
            model_name="projectservice",
            name="name",
            field=models.CharField(blank=True, default="", max_length=200),
        ),
    ]
