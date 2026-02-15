from django.db import migrations, models
import core.storages


class Migration(migrations.Migration):

    dependencies = [('companies', '0002_company_financial_defaults')]

    operations = [
        migrations.AlterField(
            model_name='company',
            name='logo',
            field=models.ImageField(blank=True, null=True, storage=core.storages.PublicMediaStorage(), upload_to='company_logos/'),
        ),
    ]
