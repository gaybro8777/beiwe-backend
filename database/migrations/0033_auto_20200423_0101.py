# Generated by Django 2.2.11 on 2020-04-23 01:01

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0032_custom'),
    ]

    operations = [
        migrations.AlterField(
            model_name='participant',
            name='fcm_instance_id',
            field=models.CharField(blank=True, db_index=True, max_length=256, null=True),
        ),
    ]
