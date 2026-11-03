# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0018_clockcorrection_add_s144.py
# H24 (S144): corrección "Fichaje añadido" (ADD), para partir un tramo
# fichado entero como presencia o desplazamiento, o poner una pulsación
# que falta. Un fichaje añadido no corrige ninguna pulsación: `event`,
# `old_kind` y `old_pressed_at` pasan a admitir vacío. No toca ninguna
# fila existente.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0017_worker_schedule_s141"),
    ]

    operations = [
        migrations.AlterField(
            model_name="clockcorrection",
            name="action",
            field=models.CharField(
                choices=[
                    ("CHANGE", "Cambio de hora o de tipo"),
                    ("CANCEL", "Anulación"),
                    ("ADD", "Fichaje añadido"),
                ],
                max_length=6,
                verbose_name="Corrección",
            ),
        ),
        migrations.AlterField(
            model_name="clockcorrection",
            name="event",
            field=models.OneToOneField(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="correction",
                to="hr_calendar.clockevent",
                verbose_name="Fichaje corregido",
            ),
        ),
        migrations.AlterField(
            model_name="clockcorrection",
            name="old_kind",
            field=models.CharField(
                blank=True,
                choices=[
                    ("IN", "Entrada"),
                    ("OUT", "Salida"),
                    ("CHG", "Cambio de tipo"),
                ],
                max_length=3,
                verbose_name="Tipo anterior",
            ),
        ),
        migrations.AlterField(
            model_name="clockcorrection",
            name="old_pressed_at",
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name="Hora anterior",
            ),
        ),
    ]
