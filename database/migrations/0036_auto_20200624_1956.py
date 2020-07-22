# Generated by Django 2.2.11 on 2020-06-24 19:56

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('database', '0035_auto_20200518_1908'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='absoluteschedule',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='archivedevent',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='chunkregistry',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='dashboardcolorsetting',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='dashboardgradient',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='dashboardinflection',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='decryptionkeyerror',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='devicesettings',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='encryptionerrormetadata',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='fileprocesslock',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='lineencryptionerror',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='participant',
            name='fcm_instance_id',
        ),
        migrations.RemoveField(
            model_name='pipelineregistry',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='pipelineupload',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='pipelineuploadtags',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='relativeschedule',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='researcher',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='scheduledevent',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='studyrelation',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='uploadtracking',
            name='deleted',
        ),
        migrations.RemoveField(
            model_name='weeklyschedule',
            name='deleted',
        ),
        migrations.CreateModel(
            name='ParticipantFCMHistory',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_on', models.DateTimeField(auto_now_add=True)),
                ('last_updated', models.DateTimeField(auto_now=True)),
                ('token', models.CharField(db_index=True, max_length=256, unique=True)),
                ('unregistered', models.DateTimeField(null=True)),
                ('participant', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='fcm_tokens', to='database.Participant')),
            ],
            options={
                'abstract': False,
            },
        ),
    ]
