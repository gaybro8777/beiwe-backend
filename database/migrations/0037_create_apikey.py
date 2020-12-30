# Generated by Django 2.2.11 on 2020-06-30 13:15

import database.validators
import django.core.validators
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0036_auto_20200624_1956'),
    ]

    operations = [
        migrations.AlterField(
            model_name='study',
            name='object_id',
            field=models.CharField(help_text='Permanent UUID attached to this study', max_length=24, unique=True, validators=[database.validators.LengthValidator(24)]),
        ),
        migrations.CreateModel(
            name='ApiKey',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('access_key_id', models.CharField(max_length=64, unique=True, validators=[django.core.validators.RegexValidator('^[0-9a-zA-Z+/]+={0,2}$')])),
                ('access_key_secret', models.CharField(max_length=44, validators=[django.core.validators.RegexValidator('^[0-9a-zA-Z_\\-]+={0,2}$')])),
                ('access_key_secret_salt', models.CharField(max_length=24, validators=[django.core.validators.RegexValidator('^[0-9a-zA-Z_\\-]+={0,2}$')])),
                ('is_active', models.BooleanField(default=True)),
                ('has_tableau_api_permissions', models.BooleanField(default=False)),
                ('researcher', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='api_keys', to='database.Researcher')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
