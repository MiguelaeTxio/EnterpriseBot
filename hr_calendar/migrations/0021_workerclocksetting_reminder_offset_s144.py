# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0021_workerclocksetting_reminder_offset_s144.py
# H24 (S144): cada trabajador elige en su página de fichaje cuándo recibe
# el recordatorio (de 15 minutos antes a 15 después de la hora del
# horario, de 5 en 5). Vacío en todas las filas existentes: les toca el
# de la empresa (ClockSettings.reminder_offset_minutes, 5 minutos antes).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0020_clocksettings_reminder_offset_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="workerclocksetting",
            name="reminder_offset_minutes",
            field=models.SmallIntegerField(
                blank=True,
                choices=[
                    (-15, "15 minutos antes"),
                    (-10, "10 minutos antes"),
                    (-5, "5 minutos antes"),
                    (0, "A la hora en punto"),
                    (5, "5 minutos después"),
                    (10, "10 minutos después"),
                    (15, "15 minutos después"),
                ],
                help_text="Minutos respecto de la hora de entrada o de "
                          "salida del horario (negativo, antes). Vacío: "
                          "el de la empresa.",
                null=True,
                verbose_name="Cuándo recibe el recordatorio",
            ),
        ),
    ]
