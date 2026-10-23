# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0020_gasoges_vehicle_id_s135.py
# H30 (S135): ID del vehículo de GasoGes en el centro de gasto, para
# enlazar los suministros del surtidor. Campo nulo y único, sin valor
# que rellenar en filas existentes (lo rellena link_gasoges_vehicles).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0019_service_crane_hours_s131'),
    ]

    operations = [
        migrations.AddField(
            model_name='machineasset',
            name='gasoges_vehicle_id',
            field=models.PositiveIntegerField(
                blank=True,
                help_text=(
                    'ID del vehículo en el programa del surtidor '
                    '(GasoGes). Vacío: sin enlace.'
                ),
                null=True,
                unique=True,
                verbose_name='ID de vehículo en GasoGes',
            ),
        ),
    ]
