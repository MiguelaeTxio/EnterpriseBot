# /home/MiguelAeTxio/PROJECTS/EnterpriseBot/ivr_config/migrations/0056_workdayscheduleday_holiday_s144.py
# H24 (S144): fila "Festivos" (7) en los días de un horario según el día,
# con las horas de los festivos cuando el horario tiene "Se trabaja en
# festivos". Solo cambian las opciones del campo: no toca ninguna fila.

from django.db import migrations, models

WEEKDAY_CHOICES = [
    (0, "Lunes"),
    (1, "Martes"),
    (2, "Miércoles"),
    (3, "Jueves"),
    (4, "Viernes"),
    (5, "Sábado"),
    (6, "Domingo"),
    (7, "Festivos"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("ivr_config", "0055_workdayschedule_works_holidays_s144"),
    ]

    operations = [
        migrations.AlterField(
            model_name="workdayscheduleday",
            name="weekday",
            field=models.PositiveSmallIntegerField(
                choices=WEEKDAY_CHOICES,
                verbose_name="Día de la semana",
            ),
        ),
    ]
