# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0021_gasoges_tables_s135.py
# H30 (S135): tablas de GasoGes (vehículos, usuarios y suministros) y
# origen de las lecturas. Una máquina puede tener varios registros de
# GasoGes en uso (A56: 119 y 120), así que el campo único
# MachineAsset.gasoges_vehicle_id (0020) pasa a GasoGesVehicle: los
# enlaces ya hechos se copian y el campo se quita.

import django.db.models.deletion
from django.db import migrations, models


def copy_links(apps, schema_editor):
    MachineAsset = apps.get_model('fleet', 'MachineAsset')
    GasoGesVehicle = apps.get_model('fleet', 'GasoGesVehicle')
    for asset in MachineAsset.objects.filter(
            gasoges_vehicle_id__isnull=False):
        GasoGesVehicle.objects.get_or_create(
            gasoges_id=asset.gasoges_vehicle_id,
            defaults={
                'machine_id': asset.pk,
                'link_method': 'enlace S135 (link_gasoges_vehicles)',
            },
        )


def copy_links_back(apps, schema_editor):
    MachineAsset = apps.get_model('fleet', 'MachineAsset')
    GasoGesVehicle = apps.get_model('fleet', 'GasoGesVehicle')
    for vehicle in GasoGesVehicle.objects.filter(machine__isnull=False):
        MachineAsset.objects.filter(
            pk=vehicle.machine_id, gasoges_vehicle_id__isnull=True,
        ).update(gasoges_vehicle_id=vehicle.gasoges_id)


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0020_gasoges_vehicle_id_s135'),
        ('document_explorer', '0191_seed_v16_catalog_item_s135'),
    ]

    operations = [
        migrations.AddField(
            model_name='machinemeterreading',
            name='source',
            field=models.CharField(
                choices=[
                    ('MANUAL', 'A mano'),
                    ('GASOGES', 'Surtidor (GasoGes)'),
                ],
                default='MANUAL',
                max_length=10,
                verbose_name='Origen',
            ),
        ),
        migrations.CreateModel(
            name='GasoGesVehicle',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID')),
                ('gasoges_id', models.PositiveIntegerField(
                    unique=True, verbose_name='ID en GasoGes')),
                ('plate', models.CharField(
                    blank=True, max_length=50,
                    verbose_name='Matrícula (GasoGes)')),
                ('name', models.CharField(
                    blank=True, max_length=150,
                    verbose_name='Nombre (GasoGes)')),
                ('link_method', models.CharField(
                    blank=True, max_length=40,
                    verbose_name='Cómo se enlazó')),
                ('unit', models.CharField(
                    choices=[
                        ('UNKNOWN', 'Sin saber'),
                        ('KM', 'Kilómetros'),
                        ('HOURS', 'Horas'),
                    ],
                    default='UNKNOWN', max_length=10,
                    verbose_name='Qué apunta en KM')),
                ('unit_source', models.CharField(
                    blank=True,
                    choices=[
                        ('DEDUCED', 'Deducida'),
                        ('DRIVER', 'Confirmada por el chófer'),
                        ('MANUAL', 'Puesta a mano'),
                    ],
                    max_length=10, verbose_name='Origen de la unidad')),
                ('last_km', models.BigIntegerField(
                    blank=True, null=True,
                    verbose_name='Últimos KM (GasoGes)')),
                ('updated_at', models.DateTimeField(
                    auto_now=True, verbose_name='Actualizado')),
                ('machine', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='gasoges_vehicles',
                    to='fleet.machineasset',
                    verbose_name='Centro de gasto')),
            ],
            options={
                'verbose_name': 'Vehículo de GasoGes',
                'verbose_name_plural': 'Vehículos de GasoGes',
                'ordering': ['gasoges_id'],
            },
        ),
        migrations.CreateModel(
            name='GasoGesUser',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID')),
                ('gasoges_id', models.PositiveIntegerField(
                    unique=True, verbose_name='ID en GasoGes')),
                ('name', models.CharField(
                    blank=True, max_length=150,
                    verbose_name='Nombre (GasoGes)')),
                ('match_note', models.CharField(
                    blank=True, max_length=255,
                    verbose_name='Cruce con la ficha')),
                ('updated_at', models.DateTimeField(
                    auto_now=True, verbose_name='Actualizado')),
                ('person', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='gasoges_users',
                    to='document_explorer.personidentity',
                    verbose_name='Trabajador')),
            ],
            options={
                'verbose_name': 'Usuario de GasoGes',
                'verbose_name_plural': 'Usuarios de GasoGes',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='GasoGesSupply',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID')),
                ('dedupe_key', models.CharField(
                    max_length=120, unique=True)),
                ('gasoges_user_id', models.PositiveIntegerField(
                    blank=True, null=True,
                    verbose_name='ID de usuario (GasoGes)')),
                ('supplied_at', models.DateTimeField(
                    db_index=True, verbose_name='Fecha y hora')),
                ('meter_value', models.BigIntegerField(
                    blank=True, null=True, verbose_name='KM tecleado')),
                ('litres', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=9, null=True,
                    verbose_name='Litros')),
                ('price', models.DecimalField(
                    blank=True, decimal_places=4, max_digits=9, null=True,
                    verbose_name='Precio')),
                ('pump_serial', models.BigIntegerField(
                    blank=True, null=True,
                    verbose_name='Nº de serie del surtidor')),
                ('tank_id', models.PositiveIntegerField(
                    blank=True, null=True, verbose_name='Depósito')),
                ('fuel_id', models.PositiveIntegerField(
                    blank=True, null=True, verbose_name='Combustible')),
                ('status', models.CharField(
                    choices=[
                        ('PENDING', 'Pendiente'),
                        ('READING', 'Lectura creada'),
                        ('ANOMALY', 'Lectura dudosa'),
                        ('NO_MACHINE', 'Sin centro de gasto'),
                        ('NO_UNIT', 'Sin saber si son km u horas'),
                    ],
                    db_index=True, default='PENDING', max_length=12,
                    verbose_name='Estado')),
                ('status_note', models.CharField(
                    blank=True, max_length=255, verbose_name='Motivo')),
                ('created_at', models.DateTimeField(
                    auto_now_add=True, verbose_name='Leído el')),
                ('reading', models.OneToOneField(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='gasoges_supply',
                    to='fleet.machinemeterreading',
                    verbose_name='Lectura creada')),
                ('user', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='supplies', to='fleet.gasogesuser',
                    verbose_name='Quién repostó')),
                ('vehicle', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='supplies', to='fleet.gasogesvehicle',
                    verbose_name='Vehículo (GasoGes)')),
            ],
            options={
                'verbose_name': 'Suministro de GasoGes',
                'verbose_name_plural': 'Suministros de GasoGes',
                'ordering': ['-supplied_at', '-id'],
            },
        ),
        migrations.RunPython(copy_links, copy_links_back),
        migrations.RemoveField(
            model_name='machineasset',
            name='gasoges_vehicle_id',
        ),
    ]
