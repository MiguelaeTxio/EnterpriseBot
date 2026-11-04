# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/hr_calendar/migrations/0020_clocksettings_reminder_offset_s144.py
# H24 (S144): cuándo sale el recordatorio de fichaje respecto de la hora
# de entrada o de salida del horario, configurable en la pestaña Fichajes
# (de 15 minutos antes a 15 después, de 5 en 5). Las filas existentes
# toman el valor por defecto, 5 minutos antes (Miguel Ángel: "lo vamos a
# poner para que nos avise 5 minutos antes"); hasta ahora era 15 después.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("hr_calendar", "0019_clocktype_effective_default_s144"),
    ]

    operations = [
        migrations.AddField(
            model_name="clocksettings",
            name="reminder_offset_minutes",
            field=models.SmallIntegerField(
                choices=[
                    (-15, "15 minutos antes"),
                    (-10, "10 minutos antes"),
                    (-5, "5 minutos antes"),
                    (0, "A la hora en punto"),
                    (5, "5 minutos después"),
                    (10, "10 minutos después"),
                    (15, "15 minutos después"),
                ],
                default=-5,
                help_text="Minutos respecto de la hora de entrada o de "
                          "salida del horario (negativo, antes).",
                verbose_name="Cuándo se envía el recordatorio",
            ),
        ),
    ]
