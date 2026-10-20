# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/fleet/migrations/0018_service_hours_interval_s131.py
# H30 (S131), corrección de Miguel Ángel: cada máquina pasa su revisión
# por horas a las 800 O a las 1200, nunca las dos. Las dos casillas de
# 0017 pasan a un único intervalo (800/1200), y las revisiones anotadas
# dejan de marcar a qué revisión corresponden (con horas cuentan para
# la de horas, con km para la de km). Lo ya marcado se conserva: una
# máquina con la casilla de 1200 queda en 1200; con solo la de 800, en
# 800.

from django.db import migrations, models


def copy_hours_interval(apps, schema_editor):
    """
    Booleans of 0017 -> service_hours_interval (1200 wins over 800).

    ---

    Pasa las casillas de 0017 al intervalo único (si estaban las dos,
    se queda 1200).
    """
    machine_model = apps.get_model("fleet", "MachineAsset")
    machine_model.objects.filter(service_every_800_hours=True).update(
        service_hours_interval=800,
    )
    machine_model.objects.filter(service_every_1200_hours=True).update(
        service_hours_interval=1200,
    )


class Migration(migrations.Migration):

    dependencies = [
        ('fleet', '0017_machine_service_plan_s131'),
    ]

    operations = [
        migrations.AddField(
            model_name='machineasset',
            name='service_hours_interval',
            field=models.PositiveSmallIntegerField(blank=True, choices=[(800, 'Cada 800 horas'), (1200, 'Cada 1200 horas')], help_text='Cada cuántas horas pasa la revisión esta máquina. Vacío: sin revisión por horas.', null=True, verbose_name='Revisión por horas'),
        ),
        migrations.RunPython(copy_hours_interval, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name='machineasset',
            name='service_every_800_hours',
        ),
        migrations.RemoveField(
            model_name='machineasset',
            name='service_every_1200_hours',
        ),
        migrations.RemoveField(
            model_name='machineservicerecord',
            name='covers_800_hours',
        ),
        migrations.RemoveField(
            model_name='machineservicerecord',
            name='covers_1200_hours',
        ),
        migrations.RemoveField(
            model_name='machineservicerecord',
            name='covers_km',
        ),
    ]
