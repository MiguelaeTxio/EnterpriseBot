# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0017_machine_service_plan_s131.py
# H30 (S131): plan de revisiones por horas y km de los centros de
# gasto, revisiones y lecturas manuales, y antelación de los avisos.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0016_sync_state_s120'),
        ('ivr_config', '0048_section_onboarding_enabled_s130'),
    ]

    operations = [
        migrations.AddField(
            model_name='machineasset',
            name='service_every_800_hours',
            field=models.BooleanField(default=False, verbose_name='Revisión cada 800 horas'),
        ),
        migrations.AddField(
            model_name='machineasset',
            name='service_every_1200_hours',
            field=models.BooleanField(default=False, verbose_name='Revisión cada 1200 horas'),
        ),
        migrations.AddField(
            model_name='machineasset',
            name='service_every_km',
            field=models.PositiveIntegerField(blank=True, help_text='Kilómetros entre revisiones. Vacío: sin revisión por kilómetros.', null=True, verbose_name='Revisión cada N km'),
        ),
        migrations.CreateModel(
            name='MachineServiceRecord',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('service_date', models.DateField(verbose_name='Fecha de la revisión')),
                ('hours', models.PositiveIntegerField(blank=True, null=True, verbose_name='Horas en la revisión')),
                ('km', models.PositiveIntegerField(blank=True, null=True, verbose_name='Kilómetros en la revisión')),
                ('covers_800_hours', models.BooleanField(default=False, verbose_name='Es la revisión de 800 horas')),
                ('covers_1200_hours', models.BooleanField(default=False, verbose_name='Es la revisión de 1200 horas')),
                ('covers_km', models.BooleanField(default=False, verbose_name='Es la revisión por kilómetros')),
                ('notes', models.CharField(blank=True, max_length=255, verbose_name='Observaciones')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Anotada el')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ivr_config.companyuser', verbose_name='Anotada por')),
                ('machine', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='service_records', to='fleet.machineasset', verbose_name='Centro de gasto')),
            ],
            options={
                'verbose_name': 'Revisión de centro de gasto',
                'verbose_name_plural': 'Revisiones de centros de gasto',
                'ordering': ['-service_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='MachineMeterReading',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reading_date', models.DateField(verbose_name='Fecha de la lectura')),
                ('hours', models.PositiveIntegerField(blank=True, null=True, verbose_name='Horas')),
                ('km', models.PositiveIntegerField(blank=True, null=True, verbose_name='Kilómetros')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Anotada el')),
                ('created_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ivr_config.companyuser', verbose_name='Anotada por')),
                ('machine', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='meter_readings', to='fleet.machineasset', verbose_name='Centro de gasto')),
            ],
            options={
                'verbose_name': 'Lectura de horas y kilómetros',
                'verbose_name_plural': 'Lecturas de horas y kilómetros',
                'ordering': ['-reading_date', '-id'],
            },
        ),
        migrations.CreateModel(
            name='MachineServiceAlertSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('hours_advance', models.PositiveIntegerField(blank=True, null=True, verbose_name='Avisar con antelación de (horas)')),
                ('km_advance', models.PositiveIntegerField(blank=True, null=True, verbose_name='Avisar con antelación de (km)')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Último cambio')),
                ('company', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='machine_service_alert_settings', to='ivr_config.company', verbose_name='Empresa')),
                ('updated_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='ivr_config.companyuser', verbose_name='Último cambio por')),
            ],
            options={
                'verbose_name': 'Antelación de avisos de revisión',
                'verbose_name_plural': 'Antelación de avisos de revisión',
            },
        ),
    ]
