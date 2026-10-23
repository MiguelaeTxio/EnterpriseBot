# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0022_refuelquestion_s135.py
# H30 (S135): preguntas por WhatsApp al chófer sobre un repostaje de
# GasoGes (refuel_value_check / refuel_unit_check). Tabla nueva.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0021_gasoges_tables_s135'),
        ('document_explorer', '0191_seed_v16_catalog_item_s135'),
    ]

    operations = [
        migrations.CreateModel(
            name='RefuelQuestion',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID')),
                ('kind', models.CharField(
                    choices=[
                        ('VALUE', '¿Es correcto el dato?'),
                        ('UNIT', '¿Kilómetros u horas?'),
                    ],
                    max_length=6, verbose_name='Pregunta')),
                ('phone', models.CharField(
                    max_length=20, verbose_name='Teléfono')),
                ('status', models.CharField(
                    choices=[
                        ('SENT', 'Enviada, sin respuesta'),
                        ('AWAITING_VALUE', 'Esperando el valor correcto'),
                        ('CONFIRMED', 'El chófer dice que es correcto'),
                        ('CORRECTED', 'Corregido por el chófer'),
                        ('UNIT_SET', 'Unidad confirmada por el chófer'),
                        ('EXPIRED', 'Sin respuesta a tiempo'),
                    ],
                    db_index=True, default='SENT', max_length=16,
                    verbose_name='Estado')),
                ('message_sid', models.CharField(
                    blank=True, max_length=64)),
                ('sent_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='Enviada')),
                ('answered_at', models.DateTimeField(
                    blank=True, null=True, verbose_name='Respondida')),
                ('answer', models.CharField(
                    blank=True, max_length=255, verbose_name='Respuesta')),
                ('person', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='refuel_questions',
                    to='document_explorer.personidentity',
                    verbose_name='Chófer')),
                ('supply', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='questions', to='fleet.gasogessupply',
                    verbose_name='Repostaje')),
                ('vehicle', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='questions', to='fleet.gasogesvehicle',
                    verbose_name='Vehículo (GasoGes)')),
            ],
            options={
                'verbose_name': 'Pregunta de repostaje',
                'verbose_name_plural': 'Preguntas de repostaje',
                'ordering': ['-sent_at', '-id'],
            },
        ),
    ]
