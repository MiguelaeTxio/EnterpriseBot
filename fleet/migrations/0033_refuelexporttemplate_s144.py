# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0033_refuelexporttemplate_s144.py
# H30 (S144): plantillas de exportación a Excel de Repostajes, una por
# vista (repostajes, vehículos, repostadores, preguntas). Tabla nueva.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0032_gasogessupply_hours_issue_s141'),
        ('ivr_config', '0053_workday_schedule_all_year_s141'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefuelExportTemplate',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID')),
                ('view', models.CharField(
                    choices=[
                        ('supplies', 'Repostajes'),
                        ('vehicles', 'Vehículos'),
                        ('users', 'Repostadores'),
                        ('questions', 'Preguntas por WhatsApp'),
                    ],
                    default='supplies', max_length=10,
                    verbose_name='Vista')),
                ('is_global', models.BooleanField(
                    default=False,
                    help_text='Visible para todos; solo un ADMIN la crea o '
                              'edita.',
                    verbose_name='Plantilla global')),
                ('name', models.CharField(
                    max_length=100, verbose_name='Nombre')),
                ('is_default', models.BooleanField(
                    default=False,
                    help_text='La que sale elegida al abrir el modal (una '
                              'por usuario y vista).',
                    verbose_name='Por defecto')),
                ('columns', models.JSONField(
                    default=list,
                    help_text='Claves de columna, en el orden del Excel.',
                    verbose_name='Columnas')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('company', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='refuel_export_templates',
                    to='ivr_config.company', verbose_name='Empresa')),
                ('company_user', models.ForeignKey(
                    blank=True,
                    help_text='Dueño de la plantilla personal; vacío en '
                              'las globales.',
                    null=True,
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='refuel_export_templates',
                    to='ivr_config.companyuser', verbose_name='Usuario')),
            ],
            options={
                'verbose_name': 'Plantilla de exportación de repostajes',
                'verbose_name_plural':
                    'Plantillas de exportación de repostajes',
                'ordering': ['view', '-is_global', '-is_default', 'name'],
            },
        ),
    ]
