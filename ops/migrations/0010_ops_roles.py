from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("ops", "0009_siteconfig_stripe_mirror_and_ops_2fa"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="OpsRoleAssignment",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(db_index=True, default=django.utils.timezone.now)),
                ("role", models.CharField(choices=[("viewer", "Viewer"), ("support", "Support"), ("finance", "Finance"), ("superops", "Super Ops")], db_index=True, max_length=24)),
                ("granted_by_email", models.EmailField(blank=True, db_index=True, default="", max_length=254)),
                ("notes", models.CharField(blank=True, default="", max_length=240)),
                ("granted_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="granted_ops_roles", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="ops_role_assignments", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "ordering": ["role", "user__email"],
                "unique_together": {("user", "role")},
            },
        ),
        migrations.AddIndex(
            model_name="opsroleassignment",
            index=models.Index(fields=["role", "created_at"], name="ops_opsrole_role_created_idx"),
        ),
        migrations.AddIndex(
            model_name="opsroleassignment",
            index=models.Index(fields=["user", "created_at"], name="ops_opsrole_user_created_idx"),
        ),
    ]
