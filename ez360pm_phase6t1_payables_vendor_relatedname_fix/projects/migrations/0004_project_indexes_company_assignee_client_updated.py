from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("projects", "0003_projectservice_name_optional"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="project",
            index=models.Index(fields=["company", "assigned_to"], name="proj_co_assignee_idx"),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(fields=["company", "client"], name="proj_co_client_idx"),
        ),
        migrations.AddIndex(
            model_name="project",
            index=models.Index(fields=["company", "updated_at"], name="proj_co_updated_idx"),
        ),
    ]
