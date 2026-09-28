# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/document_explorer/migrations/0156_requirementalertrule_s122.py
"""
H30 (S122, punto 2). Configuración de avisos por tipo documental
obligatorio dentro de cada requisito de documentación
(RequirementAlertRule). Tabla nueva, sin datos que migrar: todo
apagado por defecto.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('document_explorer', '0155_bigautofield_ids_s121'),
    ]

    operations = [
        migrations.CreateModel(
            name='RequirementAlertRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notify_missing', models.BooleanField(default=False, verbose_name='Avisar si falta')),
                ('notify_30_days', models.BooleanField(default=False, verbose_name='Avisar 30 días antes')),
                ('notify_15_days', models.BooleanField(default=False, verbose_name='Avisar 15 días antes')),
                ('notify_7_days', models.BooleanField(default=False, verbose_name='Avisar 7 días antes')),
                ('notify_day_before', models.BooleanField(default=False, verbose_name='Avisar el día anterior')),
                ('custom_1_value', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Aviso personalizado 1 -- antelación')),
                ('custom_1_unit', models.CharField(blank=True, choices=[('DAYS', 'días'), ('MONTHS', 'meses')], max_length=6, verbose_name='Aviso personalizado 1 -- unidad')),
                ('custom_2_value', models.PositiveSmallIntegerField(blank=True, null=True, verbose_name='Aviso personalizado 2 -- antelación')),
                ('custom_2_unit', models.CharField(blank=True, choices=[('DAYS', 'días'), ('MONTHS', 'meses')], max_length=6, verbose_name='Aviso personalizado 2 -- unidad')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Última edición')),
                ('document_type', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='requirement_alert_rules', to='document_explorer.documenttypecatalog', verbose_name='Tipo documental')),
                ('job_position', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='alert_rules', to='document_explorer.jobposition', verbose_name='Requisito de documentación')),
            ],
            options={
                'verbose_name': 'Aviso de requisito de documentación',
                'verbose_name_plural': 'Avisos de requisitos de documentación',
                'constraints': [models.UniqueConstraint(fields=('job_position', 'document_type'), name='unique_alert_rule_per_position_type')],
            },
        ),
    ]
