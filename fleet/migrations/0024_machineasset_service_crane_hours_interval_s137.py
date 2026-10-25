# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0024_machineasset_service_crane_hours_interval_s137.py
# H30 (S137): la grúa tiene su propio intervalo de revisión por horas,
# separado del del camión (Miguel Ángel: "la grúa que va en horas y el
# camión que va en km"). Hasta ahora la revisión de grúa tomaba el
# intervalo de service_hours_interval; para no cambiar ningún aviso
# existente, las máquinas con horómetro de grúa y revisión por horas
# copian ese intervalo al campo nuevo.

from django.db import migrations, models


def copy_crane_interval(apps, schema_editor):
    """
    Keep the current crane schedules: copy the hours interval.

    ---

    Conserva las revisiones de grúa que ya existían: copia el
    intervalo de horas a las máquinas con horómetro de grúa.
    """
    machine_asset = apps.get_model("fleet", "MachineAsset")
    machine_asset.objects.filter(
        has_crane_hours=True, service_hours_interval__isnull=False,
    ).update(service_crane_hours_interval=models.F("service_hours_interval"))


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0023_gasogesvehicle_ask_driver_s135'),
    ]

    operations = [
        migrations.AddField(
            model_name='machineasset',
            name='service_crane_hours_interval',
            field=models.PositiveSmallIntegerField(
                blank=True,
                choices=[(800, 'Cada 800 horas'), (1200, 'Cada 1200 horas')],
                help_text=(
                    'Cada cuántas horas de grúa pasa la revisión la grúa. '
                    'Vacío: sin revisión de grúa. Solo cuenta si tiene '
                    'horómetro de grúa.'
                ),
                null=True,
                verbose_name='Revisión de la grúa por horas',
            ),
        ),
        migrations.RunPython(copy_crane_interval, migrations.RunPython.noop),
    ]
