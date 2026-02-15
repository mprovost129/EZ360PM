from django.db import migrations, models
import core.storages


class Migration(migrations.Migration):

    dependencies = [('expenses', '0001_initial')]

    operations = [
        migrations.AlterField(
            model_name='expense',
            name='receipt',
            field=models.FileField(blank=True, null=True, storage=core.storages.PrivateMediaStorage(), upload_to='expense_receipts/'),
        ),
    ]
