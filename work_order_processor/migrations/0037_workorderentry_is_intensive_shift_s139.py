# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/work_order_processor/migrations/0037_workorderentry_is_intensive_shift_s139.py
# H30 (S139): el parte guarda si la jornada era intensiva o partida.
# Campo nuevo nulable: los partes existentes quedan sin dato (no se
# inventa con el horario de hoy); sin datos que mover.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("work_order_processor", "0036_workshop_notice_read_s137"),
    ]

    operations = [
        migrations.AddField(
            model_name="workorderentry",
            name="is_intensive_shift",
            field=models.BooleanField(
                blank=True,
                default=None,
                help_text=(
                    "Si la jornada del parte era intensiva (Sí) o partida "
                    "(No), según el horario del operario al crear el parte. "
                    "Vacío en los partes anteriores a S139 y en los de PDF "
                    "o generados."
                ),
                null=True,
                verbose_name="Jornada intensiva",
            ),
        ),
    ]
